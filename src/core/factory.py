# core/factory.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from config.config_singleton import Config
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant
from core.streaming_provider import YulYenStreamingProvider
from typing import Optional
from security.tinyguard import BasicGuard, zeigefinger_message
from ui.terminal_ui import TerminalUI
from ui.web_ui import WebUI
from core import utils

import config.personas as personas


class AppFactory:
    """
    Baut zentrale Objekte auf Basis der globalen Config (Singleton).
    SRP: KEIN Starten von Threads/Servern/Logging und KEIN launch() hier.
    Lazy-Erzeugung: Objekte werden in den Gettern erstellelt und gecached.
    """

    def __init__(self) -> None:
        self._cfg = Config()
        self._keyword_finder: Optional[SpacyKeywordFinder] = None
        self._streamer: Optional[YulYenStreamingProvider] = None
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

    
    def get_streamer_for_persona(self, persona_name: str) -> YulYenStreamingProvider:
        """Erzeugt einen neuen LLM‑Streamer für die übergebene Persona."""
        core = self._cfg.core
        persona_prompt = utils._system_prompt_with_date(persona_name, core["include_date"]) # Prompt der Persona laden
        reminder = personas.get_reminder(persona_name)  
        options = personas.get_options(persona_name)  
        log_prefix = self._cfg.logging["conversation_prefix"]
        conv_log_file = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"
        streamer = YulYenStreamingProvider(
            base_url=core["ollama_url"],
            model_name=core["model_name"],
            warm_up=bool(core.get("warm_up", False)),
            reminder=reminder,
            persona=persona_name,
            persona_prompt=persona_prompt,
            persona_options=options,
            log_file=conv_log_file,
        )

        # Security-Guard aus YAML
        sec_cfg = getattr(self._cfg, "security", None)
        if sec_cfg and sec_cfg.get("enabled"):
            guard = BasicGuard(
                enabled=True,
                prompt_injection_protection=bool(sec_cfg["prompt_injection_protection"]),
                pii_protection=bool(sec_cfg["pii_protection"]),
                output_blocklist=bool(sec_cfg["output_blocklist"]),
            )
            streamer.set_guard(guard)

        return streamer

    def get_api_provider(self):
        """Nur bauen, wenn in YAML aktiviert. Kein Serverstart hier."""
        if self._api_provider is None:
            if not bool(self._cfg.api["enabled"]):
                return None
            from api.provider import AiApiProvider
            self._api_provider = AiApiProvider(
                self.get_streamer_for_persona("DORIS"), # PETER als default für API-Calls
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
        finder   = self.get_keyword_finder()
        wiki     = self._cfg.wiki

        if ui_type == "terminal":
            self._ui = TerminalUI(
                self, self._cfg, finder, utils._local_ip,
                int(wiki["snippet_limit"]), wiki["mode"], int(wiki["proxy_port"]),
                wiki_timeout=(float(wiki["timeout_connect"]), float(wiki["timeout_read"])),
            )
        elif ui_type == "web":
            web_cfg = self._cfg.ui["web"]               
            host    = web_cfg["host"]                  
            port    = int(web_cfg["port"])
            self._ui = WebUI(
                 self, self._cfg, finder, utils._local_ip,
                int(wiki["snippet_limit"]), wiki["mode"], int(wiki["proxy_port"]),
                web_host=host, web_port=port,
                wiki_timeout=(float(wiki["timeout_connect"]), float(wiki["timeout_read"])),
            )
        else:
            raise ValueError(f"Unbekannter UI-Typ: {ui_type!r} (erwarte 'web' oder 'terminal')")

        return self._ui
