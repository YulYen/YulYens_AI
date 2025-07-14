# leah_main.py

from terminal_ui import TerminalUI
from web_ui import WebUI

# --- Konfiguration ---
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "leah13b1"
ENABLE_LOGGING = True
GREETING = "Chatte mit L-E-A-H in der Modellversion "+ MODEL_NAME

#ui = TerminalUI(MODEL_NAME,GREETING, OLLAMA_URL, ENABLE_LOGGING)
ui = WebUI(MODEL_NAME, GREETING, OLLAMA_URL, ENABLE_LOGGING)


def main():
    ui.launch()

if __name__ == "__main__":
    main()
hasattr