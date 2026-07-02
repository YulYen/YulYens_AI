# wikipedia-proxy.py
import json
import logging
import re
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup
from config.config_singleton import Config

# --- Configuration --------------------------------------------------------------


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


class _ProxySettings:
    """Reads all proxy settings from the Config once, on first use (not at import)."""

    def __init__(self, config: Config):
        self.config = config
        wiki_cfg = config.wiki
        offline_cfg = wiki_cfg["offline"]

        online_map = wiki_cfg.get("online_base_url_map", {}) or {}
        self.online_base_url = _normalize_base_url(
            online_map.get(config.language)
            or f"https://{config.language}.wikipedia.org"
        )

        self.snippet_limit = int(wiki_cfg["snippet_limit"])
        self.timeout = (
            float(wiki_cfg["timeout_connect"]),
            float(wiki_cfg["timeout_read"]),
        )
        self.kiwix_port = int(offline_cfg["kiwix_port"])
        self.kiwix_host = offline_cfg["host"]
        self.proxy_port = int(wiki_cfg["proxy_port"])
        self.zim_prefix = offline_cfg["zim_prefix"]


_settings: _ProxySettings | None = None


def _get_settings() -> _ProxySettings:
    global _settings
    if _settings is None:
        _settings = _ProxySettings(Config())
    return _settings


# --- Configure logging ----------------------------------------------------------
logger = logging.getLogger("wiki_proxy")
logger.info("Wiki proxy starting up…")


# ---------- Helpers for responses -----------------------------------------------
def _send_bytes(
    handler: BaseHTTPRequestHandler, status: int, content_type: str, body: bytes
):
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


# ---------- Helpers for request processing -------------------------------------
def _build_kiwix_url(term: str) -> str:
    s = _get_settings()
    return f"http://{s.kiwix_host}:{s.kiwix_port}/{s.zim_prefix}/{term}"


def _build_online_url(term: str) -> str:
    # Wikipedia accepts underscores as spaces
    return f"{_get_settings().online_base_url}/wiki/{term}"


def _clean_whitespace_and_remove_refs(text: str) -> str:
    """
    Removes footnotes [1], soft hyphen \xad, NBSP \xa0, and folds whitespace into ' '.
    """
    # Footnotes like [1], [ 23 ]
    text = re.sub(r"\[\s*\d+\s*\]", "", text)
    # Remove soft hyphen (syllable breaks)
    text = text.replace("\xad", "")
    # Replace NBSP with a standard space
    text = text.replace("\xa0", " ")
    # Collapse all whitespace to single spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _find_infobox_table(soup):
    """
    Robustly searches for an infobox table.
    Handles different class combinations ("infobox", "infobox vcard", ...)
    and is case-insensitive.
    """

    # 1) CSS selector: direct matches
    tbl = soup.select_one("table.infobox")
    if tbl:
        return tbl

    # 2) Check whether 'infobox' appears anywhere in the class attribute list
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

        # Skip image/media rows
        if tds:
            td_classes_joined = " ".join(
                sum([td.get("class") or [] for td in tds], [])
            ).lower()
            if "image" in td_classes_joined or "infobox-image" in td_classes_joined:
                continue

        key = val = None

        if th and tds:
            # Classic case: <th>Key</th><td>Value</td>
            key = th.get_text(" ", strip=True)
            val = tds[0].get_text(" ", strip=True)

        elif len(tds) >= 2:
            # Newer case: <td class="ibleft">Key</td><td class="ibright|ibdata">Value</td>
            left = right = None
            for td in tds:
                classes = " ".join(td.get("class") or []).lower()
                if "ibleft" in classes and left is None:
                    left = td
                elif (
                    ("ibright" in classes) or ("ibdata" in classes)
                ) and right is None:
                    right = td
            if left and right:
                key = left.get_text(" ", strip=True)
                val = right.get_text(" ", strip=True)
            else:
                # Generic fallback: take the first two <td> elements
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
    Builds 'Key: Value | Key: Value …'. Values are gently shortened to keep the line brief.
    """
    if not pairs:
        return ""
    parts = []
    for k, v in pairs:
        # Trim overly long values (cut cleanly at word boundaries)
        if len(v) > 120:
            v = (v[:120].rsplit(" ", 1)[0] + " …").strip()
        parts.append(f"{k}: {v}")
    return " | ".join(parts)


def _build_user_visible_link(
    handler: BaseHTTPRequestHandler, term: str, online: bool
) -> str:
    """
    Builds a link that works in the user's browser.
    Takes the host from the current request (e.g. 192.168.x.y or localhost)
    and only adjusts the port (8042 -> 8080) for Kiwix.
    """
    host_header = handler.headers.get("Host", "localhost")
    hostname = host_header.split(":")[0] if host_header else "localhost"
    if online:
        return _build_online_url(term)
    # Local Kiwix link (same host as the user request, but port 8080)
    s = _get_settings()
    return f"http://{hostname}:{s.kiwix_port}/{s.zim_prefix}/{term}"


def _build_wiki_hint(cfg, online: bool, persona_name: str, link: str) -> str:
    """
    Builds the prefix from config.yaml (online/offline) and appends the link.
    """
    key = "wiki_lookup_prefix_online" if online else "wiki_lookup_prefix_offline"
    tpl = cfg.texts[
        key
    ]  # Intentionally allow KeyError if config.yaml is missing the key
    prefix = tpl.format(
        persona_name=persona_name, project_name=cfg.texts["project_name"]
    )
    return f"{prefix}\n{link}"


def _parse_limit(query: dict) -> int:
    snippet_limit = _get_settings().snippet_limit
    try:
        val = int(query.get("limit", [snippet_limit])[0])
    except (ValueError, TypeError):
        val = snippet_limit
    return max(0, min(val, snippet_limit))


def _fetch_kiwix(term: str):
    url = _build_kiwix_url(term)
    logger.info(f"[Fetch] {url}")
    start_kiwix = time.perf_counter()
    try:
        r = requests.get(url, timeout=_get_settings().timeout)
        return r.status_code, r
    except Exception as e:
        logger.error(f"[FetchError] {e}")
        return 500, None
    finally:
        # Immer Gesamtdauer loggen
        duration_total = (time.perf_counter() - start_kiwix) * 1000
        logger.info(
            f'[_fetch_kiwix] Request "{term}" answered in {duration_total:.1f} ms'
        )


def _fetch_online(term: str):
    """Fetches a short text from the configured live Wikipedia (REST Summary API)."""
    s = _get_settings()
    url = f"{s.online_base_url}/api/rest_v1/page/summary/{term}"
    logger.info(f"[FetchOnline] {url}")
    try:
        r = requests.get(
            url, timeout=s.timeout, headers={"User-Agent": "LeahWikiProxy/1.0"}
        )
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
    # Redirect standard HTTPServer logs into our logger (optional but nice)
    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        start_total = time.perf_counter()
        try:
            parsed_path = urlparse(self.path)
            search_term = unquote(parsed_path.path[1:])
            query = parse_qs(parsed_path.query)
            online = query.get("online", ["0"])[0] == "1"
            persona = query.get("persona", ["0"])[0]

            logger.info(
                f"[Request] term='{search_term}' path='{self.path}' online={online}"
            )

            if not search_term:
                _send_text(self, 400, "Search term missing. Example: /Albert_Einstein")
                return

            if online:
                status, resp = _fetch_online(search_term)
            else:
                status, resp = _fetch_kiwix(search_term)

            if status != 200:
                if status == 404:
                    logger.info(f"[NotFound] 404 for '{search_term}'")
                    _send_text(self, 404, "Article not found.")
                else:
                    logger.error(f"[Error] HTTP status {status} for '{search_term}'")
                    _send_text(self, 500, f"Unexpected error – HTTP status: {status}")
                return

            # Extract content
            if online:
                clean_text = _clean_whitespace_and_remove_refs(resp.text)
                kv_line = ""  # Online summaries do not include an HTML infobox
            else:
                html_bytes = resp.content
                soup = BeautifulSoup(html_bytes, "html.parser")
                # 1) Extract key/value pairs from the original HTML
                kv_pairs = _extract_infobox_kv(resp.text)
                kv_line = _format_kv_line(kv_pairs)

                # 2) Remove the infobox from the DOM so it does NOT appear in the body text
                ibox = _find_infobox_table(soup)
                if ibox:
                    ibox.decompose()

                # 3) Extract the remaining text
                content_div = soup.find(id="content") or soup.body
                raw_text = (
                    content_div.get_text(separator="\n", strip=True)
                    if content_div
                    else ""
                )
                clean_text = _clean_whitespace_and_remove_refs(raw_text)

            # --- One-off limiting logic: keep the key/value block intact, truncate only the body ---
            limit = _parse_limit(query)

            if kv_line:
                # Key/value block + blank line + body text
                sep = "\n\n"
                base = kv_line + sep
                remaining = max(0, limit - len(base))
                body = (
                    clean_text
                    if remaining <= 0
                    else (
                        clean_text[:remaining].rsplit(" ", 1)[0] + " …"
                        if len(clean_text) > remaining
                        else clean_text
                    )
                )
                combined_text = base + body
            else:
                # No key/value block → apply the limit normally
                combined_text = (
                    clean_text
                    if len(clean_text) <= limit
                    else (clean_text[:limit].rsplit(" ", 1)[0] + " …")
                )

            clean_text = combined_text

            # Target link & UI hint
            link = _build_user_visible_link(self, search_term, online)
            source = "online" if online else "local"
            wiki_hint = _build_wiki_hint(_get_settings().config, online, persona, link)

            # Return JSON
            payload = {
                "title": search_term.replace("_", " "),
                "text": clean_text,
                "link": link,
                "source": source,
                "wiki_hint": wiki_hint,
            }
            # Make the actually-served snippet visible (this was the blind spot:
            # request + timing were logged, but never the returned text itself).
            logger.info(
                "[Snippet] term='%s' source=%s len=%d head=%r",
                search_term,
                source,
                len(clean_text),
                clean_text[:160],
            )
            _send_json(self, 200, payload)
        finally:
            # Always log the total duration
            duration_total = (time.perf_counter() - start_total) * 1000
            logger.info(
                f'[WikiProxy] Request "{query}" answered in {duration_total:.1f} ms'
            )


def run():
    proxy_port = _get_settings().proxy_port
    logger.info(f"Starting local Wikipedia text proxy at http://localhost:{proxy_port}")
    server = HTTPServer(("", proxy_port), WikiRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    run()
