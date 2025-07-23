# leah_main.py

from terminal_ui import TerminalUI
from web_ui import WebUI
from system_prompts import leah_system_prompts
import json

# --- Konfiguration ---
MODEL_NAME = "leo3"
ENABLE_LOGGING = False
GREETING = "Chatte mit L-E-A-H in der Modellversion "+ MODEL_NAME

def main():
    system_prompt = leah_system_prompts[0]["prompt"]
    #ui = TerminalUI(MODEL_NAME,GREETING, ENABLE_LOGGING, system_prompt)
    ui = WebUI(MODEL_NAME, GREETING, ENABLE_LOGGING, system_prompt)
    ui.launch()

if __name__ == "__main__":
    main()
hasattr

