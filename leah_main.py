# leah_main.py
import streaming_core
import terminal_ui

# --- Konfiguration ---
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "leah13b"
ENABLE_LOGGING = False


def main():
    # UI initialisieren
    terminal_ui.init_ui()
    terminal_ui.print_welcome(MODEL_NAME)

    history = []
    while True:
        user_input = terminal_ui.prompt_user()
        print()  # Leerzeile
        if user_input.lower() in ("exit", "quit"):
            print("👋 Auf Wiedersehen!")
            break

        history.append({"role": "user", "content": user_input})
        terminal_ui.print_bot_prefix()
        reply = streaming_core.send_message_stream(
            messages=history,
            stream_url=OLLAMA_URL,
            model_name=MODEL_NAME,
            enable_logging=ENABLE_LOGGING
        )
        print()  # Zeilenumbruch
        history.append({"role": "assistant", "content": reply})

if __name__ == "__main__":
    main()
