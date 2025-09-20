from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Type

from config.config_singleton import Config
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant
from core.streaming_provider import YulYenStreamingProvider
from security.tinyguard import BasicGuard, create_guard
from ui.terminal_ui import TerminalUI
from ui.web_ui import WebUI
from core import utils
from core.dummy_llm_core import DummyLLMCore
from core.llm_core import LLMCore

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
                variant = self._resolve_spacy_model_variant()
                self._keyword_finder = SpacyKeywordFinder(variant)
            else:
                self._keyword_finder = None
        return self._keyword_finder

    def _resolve_spacy_model_variant(self) -> ModelVariant:
        """Ermittelt die konfigurierte spaCy-Modellvariante mit sinnvollem Fallback."""

        wiki_cfg = getattr(self._cfg, "wiki", {}) or {}
        raw_variant = wiki_cfg.get("spacy_model_variant")

        if isinstance(raw_variant, ModelVariant):
            return raw_variant

        if isinstance(raw_variant, str):
            normalized = raw_variant.strip().lower()
            for variant in ModelVariant:
                if normalized in {variant.name.lower(), variant.value.lower()}:
                    return variant

            logging.warning(
                "Unbekannte spaCy-Variante '%s' – fallback auf %s",
                raw_variant,
                ModelVariant.LARGE.value,
            )

        elif raw_variant is not None:
            logging.warning(
                "Ungültiger Typ für spaCy-Variante (%s) – fallback auf %s",
                type(raw_variant).__name__,
                ModelVariant.LARGE.value,
            )

        return ModelVariant.LARGE

    def get_streamer_for_persona(self, persona_name: str) -> YulYenStreamingProvider:
        """Erzeugt einen neuen LLM‑Streamer für die übergebene Persona."""
        core_cfg = self._cfg.core
        persona_prompt = utils._system_prompt_with_date(
            persona_name, core_cfg["include_date"]
        )
        options = personas.get_options(persona_name)
        log_prefix = self._cfg.logging["conversation_prefix"]
        conv_log_file = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

        base_url = core_cfg.get("ollama_url")
        backend = self._determine_backend(core_cfg)
        llm_core = self._create_llm_core(backend, base_url)

        logging.debug("Erzeuge Streamer für %s mit Backend '%s'", persona_name, backend)

        streamer_base_url = base_url if base_url is not None else ""

        streamer = YulYenStreamingProvider(
            base_url=streamer_base_url,
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

    def _determine_backend(self, core_cfg: dict) -> str:
        """Liest den gewünschten LLM-Backend-Typ aus der Config."""

        raw_backend = core_cfg.get("backend", "ollama")
        if raw_backend is None:
            return "ollama"

        if isinstance(raw_backend, str):
            backend = raw_backend.strip().lower()
        else:
            backend = str(raw_backend).strip().lower()

        if not backend:
            return "ollama"

        if backend in {"ollama", "dummy"}:
            return backend

        raise ValueError(
            "Unbekannter Wert für core.backend: "
            f"{raw_backend!r}. Unterstützt werden 'ollama' und 'dummy'."
        )

    def _create_llm_core(self, backend: str, base_url: Optional[str]) -> LLMCore:
        """Erzeugt die konkrete LLM-Core-Implementierung basierend auf dem Backend."""

        if backend == "dummy":
            return DummyLLMCore()

        if backend == "ollama":
            if not base_url:
                raise KeyError(
                    "core.ollama_url muss gesetzt sein, wenn core.backend auf 'ollama' steht."
                )

            try:
                ollama_core_cls = self._load_ollama_core_class()
            except ModuleNotFoundError as exc:
                missing_name = getattr(exc, "name", None)
                message = str(exc)
                if missing_name == "ollama" or (
                    missing_name is None and "ollama" in message.lower()
                ):
                    raise RuntimeError(
                        "Das Ollama-Backend ist aktiviert (core.backend: 'ollama'), "
                        "aber das Python-Paket 'ollama' ist nicht installiert. "
                        "Installiere es mit 'pip install ollama' oder stelle core.backend auf 'dummy'."
                    ) from exc
                raise

            return ollama_core_cls(base_url=base_url)

        raise ValueError(f"Unsupported backend: {backend!r}")

    def _load_ollama_core_class(self) -> Type[LLMCore]:
        """Isolierter Import, um optionale Abhängigkeit sauber zu kapseln."""

        from core.ollama_llm_core import OllamaLLMCore

        return OllamaLLMCore

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
