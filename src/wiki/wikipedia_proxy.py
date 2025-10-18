# wikipedia-proxy.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import json, re
import logging, time
from datetime import datetime
from config.logging_setup import init_logging
from config.config_singleton import Config

# --- Konfiguration --------------------------------------------------------------
config = Config()  # Singleton-Instanz laden (lädt YAML beim ersten Aufruf)
 
WIKI_CFG = config.wiki
OFFLINE_CFG = config.wiki["offline"]

SNIPPET_LIMIT = int(WIKI_CFG["snippet_limit"])
TIMEOUT = (float(WIKI_CFG["timeout_connect"]), float(WIKI_CFG["timeout_read"]))

KIWIX_PORT = int(OFFLINE_CFG["kiwix_port"])
KIWIX_HOST = OFFLINE_CFG["host"]
PROXY_PORT = int(WIKI_CFG["proxy_port"])
ZIM_PREFIX = OFFLINE_CFG["zim_prefix"]

KIWIX_TIMEOUT = TIMEOUT
ONLINE_TIMEOUT = TIMEOUT

# --- Logging einrichten ---------------------------------------------------------
logger = logging.getLogger("wiki_proxy")
logger.info("Wiki-Proxy startet…")


# ---------- Helper für Antworten ------------------------------------------------
def _send_bytes(handler: BaseHTTPRequestHandler, status: int, content_type: str, body: bytes):
    handler.send_response(status)
    handler.send_header("Content-type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (ConnectionAbortedError, BrokenPipeError) as e:
        logger.warning(f"[ClientAborted] write aborted: {e}")

def _send_text(handler: BaseHTTPRequestHandler, status: int, text: str):
    _send_bytes(handler, status, "text/plain", text.encode("utf-8"))

def _send_json(handler: BaseHTTPRequestHandler, status: int, obj: dict):
    encoded = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    _send_bytes(handler, status, "application/json", encoded)


# ---------- Helper für Request-Verarbeitung ------------------------------------
def _build_kiwix_url(term: str) -> str:
    return f"http://{KIWIX_HOST}:{KIWIX_PORT}/{ZIM_PREFIX}/{term}"

def _build_online_url(term: str) -> str:
    # Wikipedia akzeptiert Unterstriche als Leerzeichen
    return f"https://de.wikipedia.org/wiki/{term}"

def _clean_whitespace_and_remove_refs(text: str) -> str:
    """
    Entfernt Fußnoten [1], Soft-Hyphen \xad, NBSP \xa0 und faltet Whitespace zu ' '.
    """
    # Fußnoten wie [1], [ 23 ]
    text = re.sub(r"\[\s*\d+\s*\]", "", text)
    # Soft-Hyphen (Silbentrennung) raus
    text = text.replace("\xad", "")
    # NBSP zu Leerzeichen
    text = text.replace("\xa0", " ")
    # alles auf einfache Leerzeichen
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def _find_infobox_table(soup):
    """
    Sucht robust nach einer Infobox-Tabelle.
    Berücksichtigt unterschiedliche Class-Kombis ("infobox", "infobox vcard", ...)
    und ist case-insensitive.
    """

    # 1) CSS-Selektor: direkte Treffer
    tbl = soup.select_one("table.infobox")
    if tbl:
        return tbl

    # 2) Enthält 'infobox' irgendwo in der class-Attributliste
    for t in soup.find_all("table"):
        classes = t.get("class") or []
        if any("infobox" in c.lower() for c in classes):
            return t
    return None

def _extract_infobox_kv(html: str, max_items: int = 30):
    soup = BeautifulSoup(html, "html.parser")

    table = _find_infobox_table(soup)
    if not table:
        return []

    pairs = []
    for tr in table.find_all("tr"):
        th = tr.find("th")
        tds = tr.find_all("td")

        # Bild-/Medienzeilen überspringen
        if tds:
            td_classes_joined = " ".join(sum([td.get("class") or [] for td in tds], [])).lower()
            if "image" in td_classes_joined or "infobox-image" in td_classes_joined:
                continue

        key = val = None

        if th and tds:
            # klassischer Fall: <th>Key</th><td>Value</td>
            key = th.get_text(" ", strip=True)
            val = tds[0].get_text(" ", strip=True)

        elif len(tds) >= 2:
            # neuer Fall: <td class="ibleft">Key</td><td class="ibright|ibdata">Value</td>
            left = right = None
            for td in tds:
                classes = " ".join(td.get("class") or []).lower()
                if "ibleft" in classes and left is None:
                    left = td
                elif (("ibright" in classes) or ("ibdata" in classes)) and right is None:
                    right = td
            if left and right:
                key = left.get_text(" ", strip=True)
                val = right.get_text(" ", strip=True)
            else:
                # generischer Fallback: nimm die ersten beiden td
                key = tds[0].get_text(" ", strip=True)
                val = tds[1].get_text(" ", strip=True)

        if key and val:
            key = _clean_whitespace_and_remove_refs(key)
            val = _clean_whitespace_and_remove_refs(val)
            if key and val:
                pairs.append((key, val))
                if len(pairs) >= max_items:
                    break

    return pairs

def _format_kv_line(pairs) -> str:
    """
    Baut 'Key: Value | Key: Value …'. Werte werden sanft gekürzt, damit die Zeile kurz bleibt.
    """
    if not pairs:
        return ""
    parts = []
    for k, v in pairs:
        # zu lange Werte einkürzen (sauber am Wortende)
        if len(v) > 120:
            v = (v[:120].rsplit(" ", 1)[0] + " …").strip()
        parts.append(f"{k}: {v}")
    return " | ".join(parts)

def _build_user_visible_link(handler: BaseHTTPRequestHandler, term: str, online: bool) -> str:
    """
    Baut einen Link, der im Browser des Nutzers funktioniert.
    Nimmt den Host aus dem aktuellen Request (z. B. 192.168.x.y oder localhost)
    und setzt nur den Port passend (8042 -> 8080) für Kiwix.
    """
    host_header = handler.headers.get("Host", "localhost")
    hostname = host_header.split(":")[0] if host_header else "localhost"
    if online:
        return _build_online_url(term)
    # lokaler Kiwix-Link (gleicher Host wie Nutzer-Aufruf, aber Port 8080)
    return f"http://{hostname}:{KIWIX_PORT}/{ZIM_PREFIX}/{term}"

def _build_wiki_hint(cfg, online: bool, persona_name: str, link: str) -> str:
    """
    Baut den Prefix aus config.yaml (online/offline) und fügt den Link an.
    """
    key = "wiki_lookup_prefix_online" if online else "wiki_lookup_prefix_offline"
    tpl = config.texts[key]  # KeyError erwünscht, wenn in config.yaml fehlt
    prefix = tpl.format(persona_name=persona_name, project_name=cfg.texts["project_name"])
    return f"{prefix}\n{link}"

def _parse_limit(query: dict) -> int:
    try:
        val = int(query.get("limit", [SNIPPET_LIMIT])[0])
    except (ValueError, TypeError):
        val = SNIPPET_LIMIT
    return max(0, min(val, SNIPPET_LIMIT))

def _fetch_kiwix(term: str):
    url = _build_kiwix_url(term)
    logger.info(f"[Fetch] {url}")
    start_kiwix = time.perf_counter()
    try:
        r = requests.get(url, timeout=KIWIX_TIMEOUT)
        return r.status_code, r
    except Exception as e:
        logger.error(f"[FetchError] {e}")
        return 500, None
    finally:
        # Immer Gesamtdauer loggen
        duration_total = (time.perf_counter() - start_kiwix) * 1000
        logger.info(f'[_fetch_kiwix] Anfrage "{term}" beantwortet in {duration_total:.1f} ms')
    
def _fetch_online(term: str):
    """Holt Kurztext aus echter deutscher Wikipedia (REST Summary API)."""
    url = f"https://de.wikipedia.org/api/rest_v1/page/summary/{term}"
    logger.info(f"[FetchOnline] {url}")
    try:
        r = requests.get(url, timeout=ONLINE_TIMEOUT, headers={"User-Agent": "LeahWikiProxy/1.0"})
        if r.status_code != 200:
            return r.status_code, None
        data = r.json()
        extract = (data.get("extract") or "").strip()
        if not extract:
            return 404, None
        class Resp:
            text = extract
            apparent_encoding = "utf-8"
        return 200, Resp()
    except Exception as e:
        logger.error(f"[FetchOnlineError] {e}")
        return 500, None


# ---------- HTTP-Handler --------------------------------------------------------
class WikiRequestHandler(BaseHTTPRequestHandler):
    # Standard-HTTPServer-Logs in unser logger leiten (optional, aber hübsch)
    def log_message(self, format, *args):
        logger.info("%s - %s" % (self.address_string(), format % args))

    def do_GET(self):
        start_total = time.perf_counter()
        try:
            parsed_path = urlparse(self.path)
            suchbegriff = unquote(parsed_path.path[1:])
            query = parse_qs(parsed_path.query)
            online = query.get("online", ["0"])[0] == "1"
            persona = query.get("persona", ["0"])[0]

            logger.info(f"[Anfrage] term='{suchbegriff}' path='{self.path}' online={online}")

            if not suchbegriff:
                _send_text(self, 400, "Suchbegriff fehlt. Beispiel: /Albert_Einstein")
                return

            if online:
                status, resp = _fetch_online(suchbegriff)
            else:
                status, resp = _fetch_kiwix(suchbegriff)

            if status != 200:
                if status == 404:
                    logger.info(f"[Nicht gefunden] 404 für '{suchbegriff}'")
                    _send_text(self, 404, "Artikel nicht gefunden.")
                else:
                    logger.error(f"[Fehler] HTTP-Code {status} für '{suchbegriff}'")
                    _send_text(self, 500, f"Unerwarteter Fehler – HTTP-Code: {status}")
                return

            # Text gewinnen
            if online:
                clean_text = _clean_whitespace_and_remove_refs(resp.text)
                kv_line = ""  # Online-Summary hat keine HTML-Infobox
            else:
                html_bytes = resp.content   
                soup = BeautifulSoup(html_bytes , "html.parser")
                # 1) KV aus Original-HTML holen
                kv_pairs = _extract_infobox_kv(resp.text)
                kv_line = _format_kv_line(kv_pairs)

                # 2) Infobox aus dem DOM entfernen, damit sie NICHT im Fließtext landet
                ibox = _find_infobox_table(soup)
                if ibox:
                    ibox.decompose()

                # 3) Jetzt den restlichen Text ziehen
                content_div = soup.find(id="content") or soup.body
                raw_text = content_div.get_text(separator="\n", strip=True) if content_div else ""
                clean_text = _clean_whitespace_and_remove_refs(raw_text)

            # --- EINMALIGE Limit-Logik: KV bleibt vollständig, nur Fließtext wird gekürzt ---
            limit = _parse_limit(query)

            if kv_line:
                # KV + Leerzeile + Fließtext
                sep = "\n\n"
                base = kv_line + sep
                remaining = max(0, limit - len(base))
                body = clean_text if remaining <= 0 else (clean_text[:remaining].rsplit(" ", 1)[0] + " …" if len(clean_text) > remaining else clean_text)
                combined_text = base + body
            else:
                # kein KV → normal limitieren
                combined_text = clean_text if len(clean_text) <= limit else (clean_text[:limit].rsplit(" ", 1)[0] + " …")

            clean_text = combined_text

            # Ziel-Link & UI-Hinweis
            link = _build_user_visible_link(self, suchbegriff, online)
            source = "online" if online else "local"
            wiki_hint = _build_wiki_hint(config, online, persona, link)

            # JSON ausgeben
            payload = {
            "title": suchbegriff.replace("_", " "),
            "text": clean_text,
            "link": link,
            "source": source,
            "wiki_hint": wiki_hint
            }
            _send_json(self, 200, payload)
        finally:
        # Immer Gesamtdauer loggen
            duration_total = (time.perf_counter() - start_total) * 1000
            logger.info(f'[WikiProxy] Anfrage "{query}" beantwortet in {duration_total:.1f} ms')



def run():
    logger.info(f"Starte lokalen Wikipedia-Text-Proxy auf http://localhost:{PROXY_PORT}")
    server = HTTPServer(("", PROXY_PORT), WikiRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
