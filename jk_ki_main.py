# jk_ki_main.py

import os, yaml, logging, socket
from datetime import datetime
from logging_setup import init_logging
from system_prompts import leah_system_prompts
from terminal_ui import TerminalUI
from web_ui import WebUI
from spacy_keyword_finder import SpacyKeywordFinder, ModelVariant

CONFIG_PATH = "config.yaml"


# ----------------- Konfig laden (ohne Fallbacks) -----------------
def load_config(path=CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
      - 'online' -> True 
      - alles andere -> False
    Hinweis: Wenn ihr 'online' später aktivieren wollt, hier einfach erweitern.
    """
    if isinstance(mode_val, bool):
        return mode_val
    return str(mode_val).strip().lower() == "offline" or str(mode_val).strip().lower() == "online"


# ----------------- Main -----------------
def main():
    cfg = load_config()

    # Strikte Keys (kein Defaulting)
    WIKI_CFG            = cfg["wiki"]
    MODEL_NAME         = cfg["core"]["model_name"]
    UI_TYPE            = cfg["ui"]["type"].lower()
    WIKI_MODE          = WIKI_CFG["mode"]      # z. B. "offline" / "online" / false
    WIKI_SNIPPET_LIMIT = int(WIKI_CFG["snippet_limit"])
    WIKI_PROXY_BASE = WIKI_CFG["proxy_base"]
    LOG_LEVEL          = cfg["logging"]["level"].upper()

    GREETING = format_greeting(cfg)

    # KeywordFinder nur bei wiki_mode_enabled
    keyword_finder = SpacyKeywordFinder(ModelVariant.MEDIUM) if _wiki_mode_enabled(WIKI_MODE) else None

    # Logging
    os.makedirs("logs", exist_ok=True)
    logfile = os.path.join("logs", f"jk_ki_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.log")
    init_logging(loglevel=LOG_LEVEL, logfile=logfile, to_console=False)
    logging.info("Starte JK_KI mit Logging")
    logging.info(f"ui.type={UI_TYPE}  wiki.mode={WIKI_MODE}  snippet_limit={WIKI_SNIPPET_LIMIT}")

    # Conversation-Log
    conv_log_file = f"conversation_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

    # Systemprompt
    system_prompt = format_system_prompt(leah_system_prompts[0]["prompt"])

    # UI auswählen (Signaturen wie in deinen UIs)
    if UI_TYPE == "terminal":
        ui = TerminalUI(MODEL_NAME, GREETING, system_prompt, keyword_finder, get_local_ip, conv_log_file, WIKI_SNIPPET_LIMIT,  WIKI_MODE, WIKI_PROXY_BASE)
    elif UI_TYPE == "web":
        ui = WebUI(MODEL_NAME, GREETING, system_prompt, keyword_finder, get_local_ip, conv_log_file, WIKI_SNIPPET_LIMIT, WIKI_MODE, WIKI_PROXY_BASE)
    else:
        raise ValueError(f"Unbekannter UI-Typ: {UI_TYPE!r} (erwarte 'web' oder 'terminal')")

    ui.launch()


if __name__ == "__main__":
    main()
