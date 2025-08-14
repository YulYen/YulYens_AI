# terminal_ui.py
from __future__ import annotations

from colorama import Fore, Style, init
from typing import Callable, List, Dict, Optional

# Gemeinsame Core-Utilities & Streamer
from streaming_core_ollama import (
    OllamaStreamer,
    lookup_wiki_snippet,
    inject_wiki_context,
)


class TerminalUI:
    """
    Terminal-Chat für Leah – nutzt die gleiche Wiki-Logik wie die WebUI:
    - Wiki-Hinweis (🕵️‍♀️ …) wird NUR im Terminal angezeigt (nicht ans LLM geschickt)
    - Wiki-Snippet (falls vorhanden) wird als System-Kontext injiziert
    - Tokenweises Streaming der LLM-Antwort bleibt unverändert
    """

    def __init__(
        self,
        streamer: OllamaStreamer,
        greeting: str,
        keyword_finder,                 # None oder SpacyKeywordFinder
        ip_func: Callable[[], str],     # z. B. jk_ki_main.get_local_ip
        wiki_snippet_limit: int,
        wiki_mode: str,                 # "offline" | "online" | False/None
        proxy_base: str,
    ):
        self.streamer = streamer
        self.greeting = greeting
        self.keyword_finder = keyword_finder
        self._ip_func = ip_func

        self.wiki_snippet_limit = int(wiki_snippet_limit)
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base

        # Nur echte Konversation (User/Assistant) + ggf. System-Kontexte (Wiki)
        self.history: List[Dict[str, str]] = []

        # Für optionale Folge-Logik (nicht zwingend genutzt, aber praktisch)
        self._last_wiki_title: Optional[str] = None

    # ---------- kleine UI‑Hilfen ----------
    def init_ui(self) -> None:
        init(autoreset=True)

    def print_welcome(self) -> None:
        print(self.greeting)
        print(f"{Fore.MAGENTA}('exit' zum Beenden){Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}('clear' für neue Unterhaltung){Style.RESET_ALL}")

    def prompt_user(self) -> str:
        return input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()

    def print_bot_prefix(self) -> None:
        print(f"{Fore.CYAN}🧠 Leah:{Style.RESET_ALL} ", end="", flush=True)

    def print_stream(self, text: str) -> None:
        print(text, end="", flush=True)

    def print_exit(self) -> None:
        print("👋 Auf Wiedersehen!")

    def local_ip(self) -> str:
        try:
            return self._ip_func()
        except Exception:
            # Fallback (sollte selten nötig sein)
            import socket
            return socket.gethostbyname(socket.gethostname())

    # ---------- Haupt-Loop ----------
    def launch(self) -> None:
        self.init_ui()
        self.print_welcome()

        while True:
            user_input = self.prompt_user()
            print()  # kleine Leerzeile nach der Eingabe

            # Exit
            if user_input.lower() in ("exit", "quit"):
                self.print_exit()
                break

            # Clear / neue Unterhaltung
            if user_input.lower() == "clear":
                self.history.clear()
                self._last_wiki_title = None
                print(f"{Fore.BLUE}🔄 Neue Unterhaltung gestartet.{Style.RESET_ALL}\n")
                continue

            # --- (1) Wiki‑Lookup: nur Top‑Treffer, Hinweis anzeigen, Snippet ggf. injizieren ---
            wiki_hint = None
            if self.keyword_finder:
                wiki_hint, title, snippet = lookup_wiki_snippet(
                    user_input,
                    self.keyword_finder,
                    self.wiki_mode,
                    self.proxy_base,
                    self.wiki_snippet_limit,
                )

                # Hinweis (🕵️‍♀️ …) NUR anzeigen – nicht an das LLM schicken
                if wiki_hint:
                    print(f"{Fore.YELLOW}{wiki_hint}{Style.RESET_ALL}\n")

                # Snippet als System-Kontext einfügen (Guardrail + Kontext)
                if snippet:
                    inject_wiki_context(self.history, title, snippet)
                    self._last_wiki_title = title

            # --- (2) Nutzerfrage an die History hängen ---
            self.history.append({"role": "user", "content": user_input})

            # --- (3) Streaming der Antwort (tokenweise) ---
            self.print_bot_prefix()
            reply = ""
            for token in self.streamer.stream(messages=self.history):
                reply += token
                self.print_stream(token)

            # --- (4) Antwort in History übernehmen, hübscher Abschluss ---
            self.history.append({"role": "assistant", "content": reply})
            print()  # Zeilenumbruch nach kompletter Antwort
