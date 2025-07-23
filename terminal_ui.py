# terminal_ui.py

from colorama import Fore, Style, init
from streaming_core_ollama import OllamaStreamer


class TerminalUI:
    def __init__(self, model_name, greeting, enable_logging, system_prompt):
        self.model_name = model_name
        self.greeting = greeting
        self.enable_logging = enable_logging
        self.history = []
        self.system_prompt = system_prompt
        self.streamer = OllamaStreamer(model_name, enable_logging, False, system_prompt)

    def init_ui(self):
        init(autoreset=True)


    def print_welcome(self):
        print(self.greeting)
        print(f"{Fore.MAGENTA} ('exit' zum Beenden){Style.RESET_ALL}")

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
        self.print_welcome()

        while True:
            user_input = self.prompt_user()
            print()
            if user_input.lower() in ["exit", "quit"]:
                self.print_exit()
                break

            self.history.append({"role": "user", "content": user_input})
            self.print_bot_prefix()

            reply = ""
            for token in self.streamer.stream(messages=self.history):
                reply += token
                self.print_stream(token)

            self.history.append({"role": "assistant", "content": reply})
            print()