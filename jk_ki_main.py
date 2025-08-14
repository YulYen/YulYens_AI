# jk_ki_main.py
import os, yaml, logging, socket
from datetime import datetime
from logging_setup import init_logging
from system_prompts import leah_system_prompts
from terminal_ui import TerminalUI
from web_ui import WebUI
from spacy_keyword_finder import SpacyKeywordFinder, ModelVariant
from streaming_core_ollama import OllamaStreamer
import threading
import uvicorn
import time
import socket

# API-Imports
from api.app import app, set_provider
from api.provider import AiApiProvider

from config_singleton import Config 

def start_api_in_background(api_cfg, provider):
    """
    Startet Uvicorn in einem Daemon-Thread.
    """
    set_provider(provider)
    host = api_cfg["host"]
    port = int(api_cfg["port"])

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="warning") # bei Info wird die TerminalUI gestört

    t = threading.Thread(target=_run, name="LeahAPI", daemon=True)
    t.start()
    return t

def _wait_for_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """Wartet kurz, bis ein TCP-Port erreichbar ist (Best‑Effort)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False

def start_wiki_proxy_thread() -> threading.Thread | None:
    proxy_port = int(Config().wiki["proxy_port"])

    # Bereits laufend? (z. B. manuell gestartet)
    if _wait_for_port("127.0.0.1", proxy_port, timeout=0.2):
        logging.info(f"Wiki-Proxy scheint schon zu laufen (Port {proxy_port} ist erreichbar).")
        return None

    # Im selben Prozess als Thread starten
    import wikipedia_proxy as wiki_proxy  # nutzt die in wikipedia-proxy.py gesetzten Konfigwerte
    t = threading.Thread(target=wiki_proxy.run, name="WikiProxy", daemon=True)
    t.start()

    # Kurz auf Readiness warten (best-effort)
    if _wait_for_port("127.0.0.1", proxy_port, timeout=3.0):
        logging.info(f"Wiki-Proxy im Thread gestartet (Port {proxy_port}).")
    else:
        logging.warning(f"Wiki-Proxy (Port {proxy_port}) nach 3s noch nicht erreichbar.")

    return t

# ----------------- kleine Helper -----------------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    ip = s.getsockname()[0]
    s.close()
    return ip

def get_today_date():
    return datetime.now().strftime("%Y-%m-%d")

def format_system_prompt(base_prompt: str) -> str:
    today = get_today_date()
    facts = f" | Heute ist der {today}."
    return base_prompt.strip() + facts



def format_greeting() -> str:
    tpl = Config().ui["greeting"] 
    values = {
        "model_name":   Config().core["model_name"],     
        "persona_name": leah_system_prompts[0]["name"],
    }
    return tpl.format_map(values)

def _wiki_mode_enabled(mode_val) -> bool:
    """
    Steuerung für KeywordFinder:
      - 'online' oder 'offline' -> True 
      - alles andere -> False
    """
    if isinstance(mode_val, bool):
        return mode_val
    return str(mode_val).strip().lower() == "offline" or str(mode_val).strip().lower() == "online"

def build_ollama_streamer():
    cfg = Config()
    system_prompt = format_system_prompt(leah_system_prompts[0]["prompt"])
    prefix = cfg.logging["conversation_prefix"]
    conv_log_file = f"{prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
    warm_up = bool(cfg.core["warm_up"])
    return OllamaStreamer(cfg.core["model_name"], warm_up, system_prompt, conv_log_file)


def main():
    config = Config()

    WIKI_MODE          = config.wiki["mode"]
    WIKI_SNIPPET_LIMIT = int(config.wiki["snippet_limit"])
    WIKI_PROXY_PORT    = config.wiki["proxy_port"]
    WIKI_TIMEOUT       = (float(config.wiki["timeout_connect"]), float(config.wiki["timeout_read"]))

    LOG_LEVEL      = config.logging["level"].upper()
    LOG_TO_CONSOLE = bool(config.logging["to_console"])
    LOG_DIR        = config.logging["dir"]

    UI_TYPE  = config.ui["type"]
    WEB_HOST = config.ui.get("web", {}).get("host", "0.0.0.0")
    WEB_PORT = int(config.ui.get("web", {}).get("port", 0))

    API_ENABLED = bool(config.api["enabled"])
    API_HOST    = config.api["host"]
    API_PORT    = int(config.api["port"])

    GREETING = format_greeting()

    if _wiki_mode_enabled(WIKI_MODE):
        start_wiki_proxy_thread()
        keyword_finder = SpacyKeywordFinder(ModelVariant.LARGE)
    else:    
        keyword_finder = None

    streamer = build_ollama_streamer()

    os.makedirs(LOG_DIR, exist_ok=True)
    logfile = os.path.join(LOG_DIR, f"yulyen_ai_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log")
    init_logging(loglevel=LOG_LEVEL, logfile=logfile, to_console=LOG_TO_CONSOLE)
    logging.info(f"ui.type={UI_TYPE} wiki.mode={WIKI_MODE} snippet_limit={WIKI_SNIPPET_LIMIT}")

    if API_ENABLED:
        provider = AiApiProvider(
            streamer,
            keyword_finder=keyword_finder,
            wiki_mode=WIKI_MODE,
            wiki_proxy_port=WIKI_PROXY_PORT,
            wiki_snippet_limit=WIKI_SNIPPET_LIMIT,
            wiki_timeout=WIKI_TIMEOUT,
        )
        start_api_in_background({"host": API_HOST, "port": API_PORT}, provider)

    if UI_TYPE is None:
        print("[Yul Yens AI] API läuft. UI ist deaktiviert (ui.type = null).")
        threading.Event().wait()
        return
    elif UI_TYPE == "terminal":
        ui = TerminalUI(streamer, GREETING, keyword_finder, get_local_ip,
                        WIKI_SNIPPET_LIMIT, WIKI_MODE, WIKI_PROXY_PORT,
                        wiki_timeout=WIKI_TIMEOUT)
    elif UI_TYPE == "web":
        ui = WebUI(streamer, GREETING, keyword_finder, get_local_ip,
                   WIKI_SNIPPET_LIMIT, WIKI_MODE, WIKI_PROXY_PORT,
                   web_host=WEB_HOST, web_port=WEB_PORT,
                   wiki_timeout=WIKI_TIMEOUT)
    else:
        raise ValueError(f"Unbekannter UI-Typ: {UI_TYPE!r} (erwarte 'web' oder 'terminal')")

    ui.launch()


if __name__ == "__main__":
    main()
