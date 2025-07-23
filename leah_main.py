# leah_main.py

from terminal_ui import TerminalUI
from web_ui import WebUI
from system_prompts import leah_system_prompts
from datetime import datetime


# --- Konfiguration ---
MODEL_NAME = "leo3"
ENABLE_LOGGING = False
GREETING = "Chatte mit L-E-A-H in der Modellversion " + leah_system_prompts[0]["name"] + " auf Basis von " + MODEL_NAME

def get_today_date():
    return datetime.now().strftime("%Y-%m-%d")

def format_system_prompt(base_prompt: str) -> str:
    today = get_today_date()
    facts = (
        f"Merke dir diese Fakten:\n"
        f"- Heute ist der {today}.\n"
        f"- Dein Trainingsdatenstand endet im April 2023.\n"
        f"- Deine Wikipedia-Recherche geht bis Juni 2025.\n"
    )
    return base_prompt.strip() + "\n\n" + facts

def main():
    system_prompt = format_system_prompt(leah_system_prompts[0]["prompt"])
    ui = TerminalUI(MODEL_NAME,GREETING, ENABLE_LOGGING, system_prompt)
    #ui = WebUI(MODEL_NAME, GREETING, ENABLE_LOGGING, system_prompt)
    ui.launch()

if __name__ == "__main__":
    main()
hasattr

