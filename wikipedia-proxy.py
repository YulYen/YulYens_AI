# wikipedia-proxy.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import json, os, re
import logging
from datetime import datetime
from logging_setup import init_logging

# --- Logging einrichten ---------------------------------------------------------
os.makedirs("logs", exist_ok=True)
PROXY_LOGFILE = os.path.join("logs", f"wiki_proxy_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log")
init_logging(loglevel="INFO", logfile=PROXY_LOGFILE, to_console=True)
logging.info("Wiki-Proxy startet…")

# --- Konfiguration --------------------------------------------------------------
KIWIX_PORT    = 8080
PROXY_PORT    = 8042
ZIM_PREFIX    = "wikipedia_de_all_nopic_2025-06"
MAX_CHARS     = 4000
KIWIX_TIMEOUT = (3.0, 8.0)  # (connect, read) Sekunden

ONLINE_TIMEOUT = (3.0, 8.0)


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
        logging.warning(f"[ClientAborted] write aborted: {e}")

def _send_text(handler: BaseHTTPRequestHandler, status: int, text: str):
    _send_bytes(handler, status, "text/plain", text.encode("utf-8"))

def _send_json(handler: BaseHTTPRequestHandler, status: int, obj: dict):
    encoded = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    _send_bytes(handler, status, "application/json", encoded)


# ---------- Helper für Request-Verarbeitung ------------------------------------
def _build_kiwix_url(term: str) -> str:
    return f"http://localhost:{KIWIX_PORT}/{ZIM_PREFIX}/{term}"

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
    und ist case-insensitiv.
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
    soup = BeautifulSoup(html, "html.parser", from_encoding="utf-8")

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

def _build_wiki_hint(link: str, online: bool) -> str:
    where = "deutsche" if online else "lokale deutsche"
    return f"🕵️‍♀️ *Leah wirft einen Blick in die {where} Wikipedia:*\n{link}"

def _parse_limit(query: dict) -> int:
    try:
        val = int(query.get("limit", [MAX_CHARS])[0])
    except (ValueError, TypeError):
        val = MAX_CHARS
    return max(0, min(val, MAX_CHARS))

def _fetch_kiwix(term: str):
    url = _build_kiwix_url(term)
    logging.info(f"[Fetch] {url}")
    try:
        r = requests.get(url, timeout=KIWIX_TIMEOUT)
        return r.status_code, r
    except Exception as e:
        logging.error(f"[FetchError] {e}")
        return 500, None
    
def _fetch_online(term: str):
    """Holt Kurztext aus echter deutscher Wikipedia (REST Summary API)."""
    url = f"https://de.wikipedia.org/api/rest_v1/page/summary/{term}"
    logging.info(f"[FetchOnline] {url}")
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
        logging.error(f"[FetchOnlineError] {e}")
        return 500, None


# ---------- HTTP-Handler --------------------------------------------------------
class WikiRequestHandler(BaseHTTPRequestHandler):
    # Standard-HTTPServer-Logs in unser Logging leiten (optional, aber hübsch)
    def log_message(self, format, *args):
        logging.info("%s - %s" % (self.address_string(), format % args))

    def do_GET(self):
        parsed_path = urlparse(self.path)
        suchbegriff = unquote(parsed_path.path[1:])
        query = parse_qs(parsed_path.query)
        online = query.get("online", ["0"])[0] == "1"

        logging.info(f"[Anfrage] term='{suchbegriff}' path='{self.path}' online={online}")

        if not suchbegriff:
            _send_text(self, 400, "Suchbegriff fehlt. Beispiel: /Albert_Einstein")
            return

        if online:
            status, resp = _fetch_online(suchbegriff)
        else:
            status, resp = _fetch_kiwix(suchbegriff)

        if status != 200:
            if status == 404:
                logging.info(f"[Nicht gefunden] 404 für '{suchbegriff}'")
                _send_text(self, 404, "Artikel nicht gefunden.")
            else:
                logging.error(f"[Fehler] HTTP-Code {status} für '{suchbegriff}'")
                _send_text(self, 500, f"Unerwarteter Fehler – HTTP-Code: {status}")
            return

        # Text gewinnen
        if online:
            clean_text = _clean_whitespace_and_remove_refs(resp.text)
            kv_line = ""  # Online-Summary hat keine HTML-Infobox
        else:
            resp.encoding = resp.apparent_encoding or "utf-8"
            html_bytes = resp.content   
            soup = BeautifulSoup(html_bytes , "html.parser", from_encoding=resp.encoding)
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
        wiki_hint = _build_wiki_hint(link, online)

        # JSON ausgeben
        payload = {
        "title": suchbegriff.replace("_", " "),
        "text": clean_text,
        "link": link,
        "source": source,
        "wiki_hint": wiki_hint
    }
        _send_json(self, 200, payload)



def run():
    logging.info(f"Starte lokalen Wikipedia-Text-Proxy auf http://localhost:{PROXY_PORT}")
    server = HTTPServer(("", PROXY_PORT), WikiRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
