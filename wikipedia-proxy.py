# wikipedia-proxy.py
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import json

# --- Konfiguration ---
KIWIX_PORT   = 8080
PROXY_PORT   = 8042
ZIM_PREFIX   = "wikipedia_de_all_nopic_2025-06"
MAX_CHARS    = 4000
KIWIX_TIMEOUT = (3.0, 8.0)  # (connect, read) Sekunden


# ---------- Helper für Antworten -------------------------------------------------

def _send_bytes(handler: BaseHTTPRequestHandler, status: int, content_type: str, body: bytes):
    handler.send_response(status)
    handler.send_header("Content-type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Connection", "close")
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (ConnectionAbortedError, BrokenPipeError) as e:
        print(f"[ClientAborted] write aborted: {e}")

def _send_text(handler: BaseHTTPRequestHandler, status: int, text: str):
    _send_bytes(handler, status, "text/plain", text.encode("utf-8"))

def _send_json(handler: BaseHTTPRequestHandler, status: int, obj: dict):
    encoded = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    _send_bytes(handler, status, "application/json", encoded)


# ---------- Helper für Request-Verarbeitung -------------------------------------

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
    print(f"[Fetch] hole {url}")
    try:
        r = requests.get(url, timeout=KIWIX_TIMEOUT)
        return r.status_code, r
    except Exception as e:
        print(f"[FetchError] {e}")
        return 500, None


# ---------- HTTP-Handler ---------------------------------------------------------

class WikiRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        suchbegriff = unquote(parsed_path.path[1:])
        query = parse_qs(parsed_path.query)

        print(f"[Anfrage] Suchbegriff: '{suchbegriff}'")

        if not suchbegriff:
            _send_text(self, 400, "Suchbegriff fehlt. Beispiel: /Albert_Einstein")
            return

        status, resp = _fetch_kiwix(suchbegriff)

        # Fehlerfälle Kiwix
        if status == 404:
            print(f"[Nicht gefunden] HTTP-Code: 404")
            _send_text(self, 404, "Artikel nicht gefunden.")
            return

        if status != 200:
            print(f"[Fehler] HTTP-Code: {status}")
            _send_text(self, 500, f"Unerwarteter Fehler – HTTP-Code: {status}")
            return

        # HTML in Text extrahieren
        resp.encoding = resp.apparent_encoding  # beste Schätzung
        soup = BeautifulSoup(resp.text, "html.parser")
        content_div = soup.find(id="content") or soup.body
        clean_text = content_div.get_text(separator="\n", strip=True) if content_div else ""

        # Limit anwenden
        limit = _parse_limit(query)
        if len(clean_text) > limit:
            clean_text = clean_text[:limit] + "... [gekürzt]"

        # JSON oder Plain ausgeben
        if "json" in query:
            payload = {
                "title": suchbegriff.replace("_", " "),
                "text": clean_text
            }
            _send_json(self, 200, payload)
        else:
            _send_text(self, 200, clean_text)


def run():
    print(f"Starte lokalen Wikipedia-Text-Proxy auf http://localhost:{PROXY_PORT}")
    server = HTTPServer(("", PROXY_PORT), WikiRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
