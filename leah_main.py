# leah_main.py

from terminal_ui import TerminalUI
from web_ui import WebUI
import streaming_core

# --- Konfiguration ---
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "leah13b1"
ENABLE_LOGGING = False

# ui = TerminalUI()
ui = WebUI(MODEL_NAME, OLLAMA_URL, ENABLE_LOGGING)


def main():

    ui.launch()

    ui.init_ui()
    ui.print_welcome(MODEL_NAME)
    ui.launch()

    history = []
    while True:
        user_input = ui.prompt_user()
        ui.print_empty_line()
        if user_input.lower() in ("exit", "quit"):
            ui.print_exit()
            break

        history.append({"role": "user", "content": user_input})
        ui.print_bot_prefix()
        reply = streaming_core.send_message_stream(
            messages=history,
            stream_url=OLLAMA_URL,
            model_name=MODEL_NAME,
            enable_logging=ENABLE_LOGGING,
            print_callback=ui.print_stream
        )
        ui.print_empty_line()
        history.append({"role": "assistant", "content": reply})

if __name__ == "__main__":
    main()
