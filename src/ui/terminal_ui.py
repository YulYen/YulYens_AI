# terminal_ui.py
from __future__ import annotations

from colorama import Fore, Style, init
from typing import Callable, List, Dict, Optional
from config.personas import get_all_persona_names, system_prompts, get_drink
import logging
from core.utils import _greeting_text
from core.context_utils import context_near_limit, karl_prepare_quick_and_dirty


# Gemeinsame Core-Utilities & Streamer
from core.streaming_provider import (
    lookup_wiki_snippet,
    inject_wiki_context,
)


class TerminalUI:
    """
    Terminal-Chat – nutzt die gleiche Wiki-Logik wie die WebUI:
    - Wiki-Hinweis (🕵️‍♀️ …) wird NUR im Terminal angezeigt (nicht ans LLM geschickt)
    - Wiki-Snippet (falls vorhanden) wird als System-Kontext injiziert
    - Tokenweises Streaming der LLM-Antwort bleibt unverändert
    """
    def __init__(self, factory, config, keyword_finder, ip,
                 wiki_snippet_limit, wiki_mode, proxy_base,
                 wiki_timeout):
        self.factory = factory
        self.config = config
        self.keyword_finder = keyword_finder
        # ip is a function returning the local IP address
        self._ip_func = ip
        self.wiki_snippet_limit = wiki_snippet_limit
        self.wiki_mode = wiki_mode
        self.proxy_base = proxy_base
        self.wiki_timeout = wiki_timeout
        self.greeting = None # wird nach Auswahl gesetzt
        self.bot = None # wird nach Auswahl gesetzt
        self.streamer = None # wird nach Auswahl gesetzt


        # Nur echte Konversation (User/Assistant) + ggf. System-Kontexte (Wiki)
        self.history: List[Dict[str, str]] = []

        # Für optionale Folge-Logik (nicht zwingend genutzt, aber praktisch)
        self._last_wiki_title: Optional[str] = None

    def choose_persona(self) -> None:
        """Fragt den Nutzer nach der gewünschten Persona und setzt den Streamer."""
        names = get_all_persona_names()
        print("Bitte wähle eine Persona:")
        for idx, name in enumerate(names, start=1):
            # optional: kurze Beschreibung anzeigen
            desc = next(p for p in system_prompts if p["name"] == name)["description"]
            print(f"{idx}. {name} – {desc}")
        while True:
            sel = input("Nummer der gewünschten Persona: ").strip()
            try:
                choice = int(sel) - 1
                if 0 <= choice < len(names):
                    persona_name = names[choice]
                    # Streamer für gewählte Persona bauen
                    self.streamer = self.factory.get_streamer_for_persona(persona_name)
                    self.bot = persona_name
                    self.greeting = _greeting_text(self.config, self.bot)

                    print(f"Persona {self.bot} ausgewählt.")
                    break
            except ValueError:
                pass
            print("Ungültige Eingabe, bitte erneut versuchen.")

    # ---------- kleine UI‑Hilfen ----------
    def init_ui(self) -> None:
        init(autoreset=True)

    def print_welcome(self) -> None:
        print(self.greeting)
        print(f"{Fore.MAGENTA}('exit' zum Beenden){Style.RESET_ALL}")
        print(f"{Fore.MAGENTA}('clear' für neue Unterhaltung){Style.RESET_ALL}")

    def prompt_user(self) -> str:
        return input(f"{Fore.GREEN}🧑 Du:{Style.RESET_ALL} ").strip()

    def print_bot_prefix(self, bot) -> None:
        print(f"{Fore.CYAN}🧠 {bot}:{Style.RESET_ALL} ", end="", flush=True)

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
        logging.info(f"Launching TerminalUI")

        """Startet die Terminal-UI. Fragt zuerst nach der Persona-Auswahl."""
        # 1. Persona wählen, falls noch kein Streamer gesetzt
        if self.streamer is None:
            self.choose_persona()

        # 2. Begrüßung ausgeben inkl. Befehle exit und clear
        self.print_welcome()

        while True:
            user_input = self.prompt_user()
            logging.info(f"[Terminal] User: {user_input}")
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
                    self.bot,
                    self.keyword_finder,
                    self.wiki_mode,
                    self.proxy_base,
                    self.wiki_snippet_limit,
                    self.wiki_timeout,
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

            self._ensure_context_headroom()

            # --- (3) Streaming der Antwort (tokenweise) ---
            self.print_bot_prefix(self.bot)
            reply = ""
            for token in self.streamer.stream(messages=self.history):
                reply += token
                self.print_stream(token)

            # --- (4) Antwort in History übernehmen, hübscher Abschluss ---
            logging.info(f"[Terminal] {self.bot}: {reply}")

            self.history.append({"role": "assistant", "content": reply})
            # Immer ZWEI Leerzeilen nach der Antwort sicherstellen:
            # (Falls das Streaming bereits \n ausgegeben hat, ergänzen wir nur die fehlenden.)
            trailing_nl = len(reply) - len(reply.rstrip("\n"))
            for _ in range(max(0, 2 - trailing_nl)):
                print()

    def _ensure_context_headroom(self) -> None:
        """Trimmt den Verlauf, wenn das Kontextlimit fast erreicht ist."""

        if not self.streamer:
            return

        persona_options = getattr(self.streamer, "persona_options", {}) or {}

        if not context_near_limit(self.history, persona_options):
            return

        drink = get_drink(self.bot)
        print(f"Einen Moment: {self.bot} holt sich {drink} ...")

        num_ctx = persona_options.get("num_ctx")
        if not num_ctx:
            logging.info(
                "TerminalUI: Kontextlimit erreicht, aber 'num_ctx' ist nicht gesetzt."
            )
            return

        try:
            ctx_limit = int(num_ctx)
        except (TypeError, ValueError):
            logging.warning(
                "TerminalUI: Ungültiger 'num_ctx'-Wert (%r); Verlauf wird nicht gekürzt.",
                num_ctx,
            )
            return

        original_length = len(self.history)
        trimmed_history = karl_prepare_quick_and_dirty(self.history, ctx_limit)
        removed = original_length - len(trimmed_history)
        self.history = trimmed_history

        if removed > 0:
            logging.info(
                "TerminalUI: %s ältere Nachrichten entfernt, um Kontext freizugeben.",
                removed,
            )
            print(
                f"{Fore.YELLOW}Hinweis: Ältere Nachrichten wurden entfernt, um Platz zu schaffen.{Style.RESET_ALL}"
            )
