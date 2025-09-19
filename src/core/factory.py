from __future__ import annotations

from datetime import datetime
from typing import Optional

from config.config_singleton import Config
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant
from core.streaming_provider import YulYenStreamingProvider
from security.tinyguard import BasicGuard, create_guard
from ui.terminal_ui import TerminalUI
from ui.web_ui import WebUI
from core import utils
from core.ollama_llm_core import OllamaLLMCore  # neu: Kern injizieren

import config.personas as personas


class AppFactory:
    """
    Baut zentrale Objekte auf Basis der globalen Config (Singleton).
    SRP: KEIN Starten von Threads/Servern/Logging und KEIN launch() hier.
    Lazy‑Erzeugung: Objekte werden in den Gettern erstellt und gecached.
    """

    def __init__(self) -> None:
        self._cfg = Config()
        self._keyword_finder: Optional[SpacyKeywordFinder] = None
        self._streamer: Optional[YulYenStreamingProvider] = None
        self._api_provider = None
        self._ui = None  # TerminalUI oder WebUI

    # --------- Lazy‑Singleton Getter ---------
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
        core_cfg = self._cfg.core
        persona_prompt = utils._system_prompt_with_date(
            persona_name, core_cfg["include_date"]
        )
        options = personas.get_options(persona_name)
        log_prefix = self._cfg.logging["conversation_prefix"]
        conv_log_file = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

        # LLM-Core hier zentral bauen und injizieren
        llm_core = OllamaLLMCore(base_url=core_cfg["ollama_url"])

        streamer = YulYenStreamingProvider(
            base_url=core_cfg["ollama_url"],
            model_name=core_cfg["model_name"],
            warm_up=bool(core_cfg.get("warm_up", False)),
            persona=persona_name,
            persona_prompt=persona_prompt,
            persona_options=options,
            log_file=conv_log_file,
            llm_core=llm_core,  # injizieren
        )

        # Security-Guard aus YAML
        sec_cfg = getattr(self._cfg, "security", None)
        guard = self._build_guard(sec_cfg)
        if guard:
            streamer.set_guard(guard)

        return streamer

    def _build_guard(self, sec_cfg: Optional[dict]) -> Optional[BasicGuard]:
        if not isinstance(sec_cfg, dict):
            return None

        enabled = bool(sec_cfg.get("enabled", True))
        if not enabled:
            return None

        raw_guard_name = sec_cfg.get("guard", "BasicGuard")
        guard_name = "BasicGuard" if raw_guard_name is None else str(raw_guard_name).strip()
        if not guard_name:
            guard_name = "BasicGuard"

        guard_settings = dict(sec_cfg)
        guard_settings["enabled"] = enabled

        try:
            return create_guard(guard_name, guard_settings)
        except ValueError as exc:
            raise ValueError(
                f"Unbekannter Security-Guard in security.guard: {raw_guard_name!r}"
            ) from exc

    def get_api_provider(self):
        """Nur bauen, wenn in YAML aktiviert. Kein Serverstart hier."""
        if self._api_provider is None:
            if not bool(self._cfg.api["enabled"]):
                return None
            from api.provider import AiApiProvider
            self._api_provider = AiApiProvider(
                keyword_finder=self.get_keyword_finder(),
                wiki_mode=self._cfg.wiki["mode"],
                wiki_proxy_port=int(self._cfg.wiki["proxy_port"]),
                wiki_snippet_limit=int(self._cfg.wiki["snippet_limit"]),
                wiki_timeout=(
                    float(self._cfg.wiki["timeout_connect"]),
                    float(self._cfg.wiki["timeout_read"]),
                ),
                factory=self,
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

        finder = self.get_keyword_finder()
        wiki = self._cfg.wiki

        if ui_type == "terminal":
            self._ui = TerminalUI(
                self, self._cfg, finder, utils._local_ip,
                int(wiki["snippet_limit"]), wiki["mode"], int(wiki["proxy_port"]),
                wiki_timeout=(
                    float(wiki["timeout_connect"]),
                    float(wiki["timeout_read"]),
                ),
            )
        elif ui_type == "web":
            web_cfg = self._cfg.ui["web"]
            host = web_cfg["host"]
            port = int(web_cfg["port"])
            self._ui = WebUI(
                self, self._cfg, finder, utils._local_ip,
                int(wiki["snippet_limit"]), wiki["mode"], int(wiki["proxy_port"]),
                web_host=host, web_port=port,
                wiki_timeout=(
                    float(wiki["timeout_connect"]),
                    float(wiki["timeout_read"]),
                ),
            )
        else:
            raise ValueError(
                f"Unbekannter UI-Typ: {ui_type!r} (erwarte 'web' oder 'terminal')"
            )

        return self._ui
