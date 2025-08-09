# leah_main.py

from terminal_ui import TerminalUI
from web_ui import WebUI
from system_prompts import leah_system_prompts
from datetime import datetime
from logging_setup import init_logging
import logging, socket
from spacy_keyword_finder import SpacyKeywordFinder, ModelVariant


# --- Konfiguration ---
MODEL_NAME = "leo3"
ENABLE_LOGGING = False
GREETING = "Chatte mit der Modellversion " + leah_system_prompts[0]["name"] + " auf Basis von " + MODEL_NAME
keyword_finder = SpacyKeywordFinder(ModelVariant.MEDIUM)

def get_local_ip():
    try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
    except:
        return "localhost"


def get_today_date():
    return datetime.now().strftime("%Y-%m-%d")

def format_system_prompt(base_prompt: str) -> str:
    today = get_today_date()
    facts = (
        f"Merke dir diese Fakten:\n"
        f"- Heute ist der {today}.\n"
        f"- Dein Trainingsdatenstand endet im April 2023.\n"
    )
    return base_prompt.strip() + "\n\n" + facts

def main():
    # Datei-Logging aktivieren
    init_logging(loglevel="INFO", logfile="jk_ki.log", to_console=False)
    logging.info("Starte JK_KI mit Logging")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    conv_log_file = f"conversation_{timestamp}.json"
    system_prompt = format_system_prompt(leah_system_prompts[0]["prompt"])
    ui = TerminalUI(MODEL_NAME,GREETING, system_prompt, keyword_finder, get_local_ip, conv_log_file)
    #ui = WebUI(MODEL_NAME, GREETING, system_prompt, keyword_finder, get_local_ip, conv_log_file)
    ui.launch()

if __name__ == "__main__":
    main()
hasattr


   



