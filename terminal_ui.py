# terminal_ui.py
from colorama import Fore, Style, init

def init_ui():
    init(autoreset=True)


def print_welcome(model_name: str):
    print(f"{Fore.MAGENTA}💬 Starte lokalen Chat mit Leah ({model_name}) ('exit' zum Beenden){Style.RESET_ALL}")


def prompt_user() -> str:
    return input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()


def print_bot_prefix():
    print(f"{Fore.CYAN}🤖 Leah:{Style.RESET_ALL} ", end="", flush=True)


def print_stream(text: str):
    print(text, end="", flush=True)


def print_exit():
    print("👋 Auf Wiedersehen!")


def print_empty_line():
    print()
