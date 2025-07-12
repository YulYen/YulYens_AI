# terminal_ui.py

from colorama import Fore, Style, init

class TerminalUI:
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

    def print_empty_line(self):
        print()

    def launch(self):
        print("Starte mit einer Frage oder Aufforderung den Dialog mit L-E-A-H ...")
