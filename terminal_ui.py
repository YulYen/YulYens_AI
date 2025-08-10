# terminal_ui.py

from colorama import Fore, Style, init
from streaming_core_ollama import OllamaStreamer


class TerminalUI:
    def __init__(self, model_name, greeting, system_prompt, keyword_finder, ip, conv_log):
        self.model_name = model_name
        self.greeting = greeting
        self.history = []  # Nur echte Konversation (nicht: Wiki-Hinweis)
        self.system_prompt = system_prompt
        self.keyword_finder = keyword_finder
        self.streamer = OllamaStreamer(model_name, False, system_prompt, conv_log)
        self.local_ip = ip
        self.already_searched_keywords = set()  # Verhindert doppelte Wiki-Links


    def init_ui(self):
        init(autoreset=True)

    def print_welcome(self):
        print(self.greeting)
        print(f"{Fore.MAGENTA} ('exit' zum Beenden){Style.RESET_ALL}")
        print(f"{Fore.MAGENTA} ('clear' für neue Unterhaltung){Style.RESET_ALL}")

    def prompt_user(self) -> str:
        return input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()

    def print_bot_prefix(self):
        print(f"{Fore.CYAN}🧠 Leah:{Style.RESET_ALL} ", end="", flush=True)

    def print_stream(self, text: str):
        print(text, end="", flush=True)

    def print_exit(self):
        print("👋 Auf Wiedersehen!")

    def print_wiki_hint(self, keywords):
        new_keywords = [kw for kw in keywords if kw not in self.already_searched_keywords]
        if not new_keywords:
            return

        self.already_searched_keywords.update(new_keywords)

        links = [
            f"http://{self.local_ip()}:8080/content/wikipedia_de_all_nopic_2025-06/{kw}"
            for kw in new_keywords
        ]
        hint = "\n".join(links)
        print(f"\n{Fore.YELLOW}🕵️‍♀️ Leah wirft einen Blick in die lokale Wikipedia:{Style.RESET_ALL}\n{hint}\n")

    def local_ip(self):
        import socket
        return socket.gethostbyname(socket.gethostname())

    def launch(self):
        self.init_ui()
        self.print_welcome()

        while True:
            user_input = self.prompt_user()
            print()
            if user_input.lower() in ["exit", "quit"]:
                self.print_exit()
                break

            if user_input.lower() == "clear":
                self.history.clear()
                self.already_searched_keywords.clear()
                print(f"{Fore.BLUE}🔄 Neue Unterhaltung gestartet.{Style.RESET_ALL}\n")
                continue
            
            if self.keyword_finder is not None:
                # 1. Wiki-Hinweis anzeigen (nicht ins Prompt geben!)
                keywords = self.keyword_finder.find_keywords(user_input)
                self.print_wiki_hint(keywords)

            # 2. Stream starten (nur echte Konversation)
            self.history.append({"role": "user", "content": user_input})
            self.print_bot_prefix()

            reply = ""
            for token in self.streamer.stream(messages=self.history):
                reply += token
                self.print_stream(token)

            self.history.append({"role": "assistant", "content": reply})
            print()
