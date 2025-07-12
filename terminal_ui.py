# terminal_ui.py

from colorama import Fore, Style, init
import streaming_core

class TerminalUI:
    def __init__(self, model_name, stream_url, enable_logging):
        self.model_name = model_name
        self.stream_url = stream_url
        self.enable_logging = enable_logging
        self.history = []

    def init_ui(self):
        init(autoreset=True)

    def print_welcome(self, model_name: str):
        print(f"{Fore.MAGENTA}💬 Starte lokalen Chat mit Leah ({model_name}) ('exit' zum Beenden){Style.RESET_ALL}")

    def prompt_user(self) -> str:
        return input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()

    def print_bot_prefix(self):
        print(f"{Fore.CYAN}🤖 Leah:{Style.RESET_ALL} ", end="", flush=True)

    def print_stream(self, text: str):
        print(text, end="", flush=True)

    def print_exit(self):
        print("👋 Auf Wiedersehen!")

    def launch(self):
        self.init_ui()
        self.print_welcome(self.model_name)

        while True:
            user_input = self.prompt_user()
            print()
            if user_input.lower() in ["exit", "quit"]:
                self.print_exit()
                break

            self.history.append({"role": "user", "content": user_input})
            self.print_bot_prefix()

            reply = ""
            def collect_stream(token):
                nonlocal reply
                reply += token
                self.print_stream(token)

            streaming_core.send_message_stream(
                messages=self.history,
                stream_url=self.stream_url,
                model_name=self.model_name,
                enable_logging=self.enable_logging,
                print_callback=collect_stream
            )

            self.history.append({"role": "assistant", "content": reply})
            print()