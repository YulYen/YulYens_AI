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

# API-Imports
from api.app import app, set_provider
from api.provider import AiApiProvider

CONFIG_PATH = "config.yaml"


# ----------------- Konfig laden (ohne Fallbacks) -----------------
def load_config(path=CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def start_api_in_background(api_cfg, provider):
    """
    Startet Uvicorn in einem Daemon-Thread.
    """
    set_provider(provider)
    host = api_cfg["host"]
    port = int(api_cfg["port"])

    def _run():
        uvicorn.run(app, host=host, port=port, log_level="info")

    t = threading.Thread(target=_run, name="LeahAPI", daemon=True)
    t.start()
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



def format_greeting(cfg: dict) -> str:
    tpl = cfg["ui"]["greeting"]  # KeyError erwünscht, wenn nicht vorhanden
    values = {
        "model_name":   cfg["core"]["model_name"],      # KeyError erwünscht
        "persona_name": leah_system_prompts[0]["name"], # vorhanden in system_prompts
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

def build_ollama_streamer(cfg):
    """
    Factory für Streamer:
      TODO: WarmUp aus der Konfig lesen
    """
    system_prompt = format_system_prompt(leah_system_prompts[0]["prompt"])
    conv_log_file = f"conversation_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

    return OllamaStreamer(cfg["core"]["model_name"], False, system_prompt, conv_log_file)


# ----------------- Main -----------------
def main():
    cfg = load_config()

    # Strikte Keys (kein Defaulting)
    WIKI_CFG            = cfg["wiki"]
    WIKI_MODE          = WIKI_CFG["mode"]      # z. B. "offline" / "online" / false
    WIKI_SNIPPET_LIMIT = int(WIKI_CFG["snippet_limit"])
    WIKI_PROXY_BASE = WIKI_CFG["proxy_base"]
    LOG_LEVEL          = cfg["logging"]["level"].upper()

    GREETING = format_greeting(cfg)

    # KeywordFinder nur bei wiki_mode_enabled
    keyword_finder = SpacyKeywordFinder(ModelVariant.MEDIUM) if _wiki_mode_enabled(WIKI_MODE) else None
    streamer = build_ollama_streamer(cfg)      # <-- deine bestehende Fabrik / Konstruktor
    # Logging
    os.makedirs("logs", exist_ok=True)
    logfile = os.path.join("logs", f"jk_ki_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log")
    init_logging(loglevel=LOG_LEVEL, logfile=logfile, to_console=False)
    ui_type = cfg.get("ui", {}).get("type", "web")
    logging.info(f"ui.type={ui_type}  wiki.mode={WIKI_MODE}  snippet_limit={WIKI_SNIPPET_LIMIT}")


    if cfg["api"]["enabled"]:
        provider = AiApiProvider(
            streamer,
            keyword_finder=keyword_finder,
            wiki_mode=WIKI_MODE,
            wiki_proxy_base=WIKI_PROXY_BASE,
            wiki_snippet_limit=WIKI_SNIPPET_LIMIT,
        )
        start_api_in_background(cfg["api"], provider)

    # 4) UI-Auswahl
    if ui_type is None:
        # Nur API – sauber laufen lassen
        print("[Leah] API läuft. UI ist deaktiviert (ui.type = null).")
        # Blocken, damit Prozess nicht sofort endet:
        threading.Event().wait()  # simple idle
        return
    elif ui_type == "terminal":
        ui = TerminalUI(streamer, GREETING , keyword_finder, get_local_ip, WIKI_SNIPPET_LIMIT,  WIKI_MODE, WIKI_PROXY_BASE)
    elif ui_type == "web":
        ui = WebUI(streamer, GREETING, keyword_finder, get_local_ip, WIKI_SNIPPET_LIMIT, WIKI_MODE, WIKI_PROXY_BASE)
    else:
        raise ValueError(f"Unbekannter UI-Typ: {ui_type!r} (erwarte 'web' oder 'terminal')")

    ui.launch()


if __name__ == "__main__":
    main()
