from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs
import requests
from bs4 import BeautifulSoup
import json

KIWIX_PORT = 8080
PROXY_PORT = 8042
ZIM_PREFIX = "wikipedia_de_all_nopic_2025-06"  # Konstante für Pfad-Präfix
MAX_CHARS = 4000  # Maximale Zeichenanzahl für die Ausgabe

class WikiRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)
        suchbegriff = unquote(parsed_path.path[1:])
        query = parse_qs(parsed_path.query)

        print(f"[Anfrage] Suchbegriff: '{suchbegriff}'")

        if not suchbegriff:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Suchbegriff fehlt. Beispiel: /Albert_Einstein")
            return

        try:
            fetch_url = f"http://localhost:{KIWIX_PORT}/{ZIM_PREFIX}/{suchbegriff}"
            print(f"[Fetch] hole {fetch_url}")
            response = requests.get(fetch_url, timeout=5)

            if response.status_code != 200:
                print(f"[Fehler] HTTP-Code: {response.status_code}")
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Artikel nicht gefunden.")
                return

            response.encoding = response.apparent_encoding  # Automatisch beste Erkennung
            soup = BeautifulSoup(response.text, 'html.parser')
            content_div = soup.find(id="content") or soup.body
            clean_text = content_div.get_text(separator="\n", strip=True) if content_div else ""

            limit = int(query.get("limit", [MAX_CHARS])[0])
            if len(clean_text) > limit:
                clean_text = clean_text[:limit] + "... [gekürzt]"

            if "json" in query:
                payload = {
                    "title": suchbegriff.replace("_", " "),
                    "text": clean_text
                }
                encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(encoded)
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(clean_text.encode("utf-8"))

        except Exception as e:
            print(f"[Exception] {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"Fehler: {str(e)}".encode("utf-8"))


def run():
    print(f"Starte lokalen Wikipedia-Text-Proxy auf http://localhost:{PROXY_PORT}")
    server = HTTPServer(("", PROXY_PORT), WikiRequestHandler)
    server.serve_forever()

if __name__ == "__main__":
    run()
