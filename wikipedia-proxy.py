# wikipedia-proxy.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import json
import os
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
            clean_text = resp.text
        else:
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")
            content_div = soup.find(id="content") or soup.body
            clean_text = content_div.get_text(separator="\n", strip=True) if content_div else ""

        # Limit anwenden
        limit = _parse_limit(query)
        if len(clean_text) > limit:
            clean_text = clean_text[:limit] + "... [gekürzt]"

        # JSON oder Plain ausgeben
        if "json" in query:
            payload = {"title": suchbegriff.replace("_", " "), "text": clean_text}
            _send_json(self, 200, payload)
        else:
            _send_text(self, 200, clean_text)


def run():
    logging.info(f"Starte lokalen Wikipedia-Text-Proxy auf http://localhost:{PROXY_PORT}")
    server = HTTPServer(("", PROXY_PORT), WikiRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
