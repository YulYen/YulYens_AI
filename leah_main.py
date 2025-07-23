# leah_main.py

from terminal_ui import TerminalUI
from web_ui import WebUI
from system_prompts import leah_system_prompts
import json

# --- Konfiguration ---
#OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "leo3"
ENABLE_LOGGING = False
GREETING = "Chatte mit L-E-A-H in der Modellversion "+ MODEL_NAME

## TODO_ Umbauen, dass das ganze Array an die UI geht
def load_system_prompt(filepath="system_prompts.json", persona="Leah 1.0"):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        for item in data:
            if item["name"] == persona:
                return item["prompt"]
    raise ValueError(f"Systemprompt für {persona} nicht gefunden.")


def main():
    system_prompt = leah_system_prompts[0]["prompt"]
    ui = TerminalUI(MODEL_NAME,GREETING, ENABLE_LOGGING, system_prompt)
    #ui = WebUI(MODEL_NAME, GREETING, ENABLE_LOGGING)
    ui.launch()

if __name__ == "__main__":
    main()
hasattr

