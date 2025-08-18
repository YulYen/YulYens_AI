# core/factory.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from config_singleton import Config
from spacy_keyword_finder import SpacyKeywordFinder, ModelVariant
from streaming_core_ollama import OllamaStreamer
from terminal_ui import TerminalUI
from web_ui import WebUI
from core import utils

import personas


class AppFactory:
    """
    Baut zentrale Objekte auf Basis der globalen Config (Singleton).
    SRP: KEIN Starten von Threads/Servern/Logging und KEIN launch() hier.
    Lazy-Erzeugung: Objekte werden in den Gettern erstellelt und gecached.
    """

    def __init__(self) -> None:
        self._cfg = Config()
        self._keyword_finder: Optional[SpacyKeywordFinder] = None
        self._streamer: Optional[OllamaStreamer] = None
        self._api_provider = None
        self._ui = None  # TerminalUI oder WebUI

    # --------- Lazy-Singleton Getter ---------
    def get_config(self) -> Config:
        return self._cfg

    def get_keyword_finder(self) -> Optional[SpacyKeywordFinder]:
        if self._keyword_finder is None:
            if utils._wiki_mode_enabled(self._cfg.wiki["mode"]):
                self._keyword_finder = SpacyKeywordFinder(ModelVariant.LARGE)
            else:
                self._keyword_finder = None
        return self._keyword_finder

    # Als Default
    def get_streamer(self) -> OllamaStreamer:
        return self.get_streamer_for_persona("PETER")
    
    def get_streamer_for_persona(self, persona_name: str) -> OllamaStreamer:
        """Erzeugt einen neuen LLM‑Streamer für die übergebene Persona."""
        core = self._cfg.core
        persona_promot = utils._system_prompt_with_date(persona_name) # Prompt der Persona laden
        reminder = personas.get_reminder(persona_name)  
        log_prefix = self._cfg.logging["conversation_prefix"]
        conv_log_file = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
        return OllamaStreamer(
            model_name=core["model_name"],
            warm_up=bool(core.get("warm_up", False)),
            reminder=reminder,
            persona=persona_promot,
            log_file=conv_log_file,
        )

    def get_api_provider(self):
        """Nur bauen, wenn in YAML aktiviert. Kein Serverstart hier."""
        if self._api_provider is None:
            if not bool(self._cfg.api["enabled"]):
                return None
            from api.provider import AiApiProvider
            self._api_provider = AiApiProvider(
                self.get_streamer(),
                keyword_finder=self.get_keyword_finder(),
                wiki_mode=self._cfg.wiki["mode"],
                wiki_proxy_port=int(self._cfg.wiki["proxy_port"]),
                wiki_snippet_limit=int(self._cfg.wiki["snippet_limit"]),
                wiki_timeout=(float(self._cfg.wiki["timeout_connect"]),
                              float(self._cfg.wiki["timeout_read"])),
            )
        return self._api_provider

    def get_ui(self):
        """
        Baut TerminalUI oder WebUI – ohne zu starten.
        Wichtig: Kein Default für web_port → Zugriff direkt aus YAML.
        """
        if self._ui is not None:
            return self._ui

        ui_type = self._cfg.ui["type"]  # None | "terminal" | "web"
        if ui_type is None:
            self._ui = None
            return None

        streamer = self.get_streamer()
        finder   = self.get_keyword_finder()
        wiki     = self._cfg.wiki

        if ui_type == "terminal":
            self._ui = TerminalUI(
                self, self._cfg, finder, utils._local_ip,
                int(wiki["snippet_limit"]), wiki["mode"], int(wiki["proxy_port"]),
                wiki_timeout=(float(wiki["timeout_connect"]), float(wiki["timeout_read"])),
            )
        elif ui_type == "web":
            web_cfg = self._cfg.ui["web"]               # <-- kein Default
            host    = web_cfg["host"]                   # KeyError erwünscht
            port    = int(web_cfg["port"])              # KeyError erwünscht
            self._ui = WebUI(
                streamer, finder, utils._local_ip,
                int(wiki["snippet_limit"]), wiki["mode"], int(wiki["proxy_port"]),
                web_host=host, web_port=port,
                wiki_timeout=(float(wiki["timeout_connect"]), float(wiki["timeout_read"])),
            )
        else:
            raise ValueError(f"Unbekannter UI-Typ: {ui_type!r} (erwarte 'web' oder 'terminal')")

        return self._ui
