from __future__ import annotations

import logging
from datetime import datetime

import config.personas as personas
from config.config_singleton import Config
from security.tinyguard import BasicGuard, create_guard
from ui.terminal_ui import TerminalUI
from ui.web_ui import WebUI
from wiki.spacy_keyword_finder import  SpacyKeywordFinder, resolve_spacy_model

from core.dummy_llm_core import DummyLLMCore
from core.llm_core import LLMCore
from core.streaming_provider import YulYenStreamingProvider
from core.utils import _system_prompt_with_date, _wiki_mode_enabled


class AppFactory:
    """
    Builds core objects based on the global config (singleton).
    SRP: NO starting threads/servers/logging and NO launch() here.
    Lazy creation: objects are created in the getters and cached.
    """

    def __init__(self) -> None:
        self._cfg = Config()
        self._keyword_finder: SpacyKeywordFinder | None = None
        self._api_provider = None
        self._ui = None  # TerminalUI or WebUI

    # --------- Lazy‑Singleton Getter ---------
    def get_config(self) -> Config:
        return self._cfg

    def get_keyword_finder(self) -> SpacyKeywordFinder | None:
        if self._keyword_finder is None:
            if _wiki_mode_enabled(self._cfg.wiki["mode"]):
                variant = resolve_spacy_model(self._cfg)
                try:
                    self._keyword_finder = SpacyKeywordFinder(variant)
                except (OSError, ImportError) as exc:
                    logging.warning(
                        "Could not initialize spaCy keyword finder: %s. "
                        "Disabling wiki features.",
                        exc,
                    )
                    self._keyword_finder = None
            else:
                self._keyword_finder = None
        return self._keyword_finder


    def get_streamer_for_persona(self, persona_name: str) -> YulYenStreamingProvider:
        """Creates a new LLM streamer for the given persona."""
        core_cfg = self._cfg.core
        persona_prompt = _system_prompt_with_date(
            persona_name, core_cfg["include_date"]
        )
        options = personas.get_options(persona_name)
        log_prefix = self._cfg.logging["conversation_prefix"]
        conv_log_file = f"{log_prefix}_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.json"

        base_url = core_cfg.get("ollama_url")
        backend = self._determine_backend(core_cfg)
        llm_core = self._create_llm_core(backend, base_url)

        logging.debug(
            "Creating streamer for %s with backend '%s'", persona_name, backend
        )

        streamer_base_url = base_url if base_url is not None else ""

        streamer = YulYenStreamingProvider(
            base_url=streamer_base_url,
            model_name=core_cfg["model_name"],
            warm_up=bool(core_cfg.get("warm_up", False)),
            persona=persona_name,
            persona_prompt=persona_prompt,
            persona_options=options,
            log_file=conv_log_file,
            llm_core=llm_core,  # inject
        )

        # Security guard configured via YAML
        sec_cfg = getattr(self._cfg, "security", None)
        guard = self._build_guard(sec_cfg)
        if guard:
            streamer.set_guard(guard)

        return streamer

    def _determine_backend(self, core_cfg: dict) -> str:
        """Reads the desired LLM backend type from the config."""

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
            "Unknown value for core.backend: "
            f"{raw_backend!r}. Supported options are 'ollama' and 'dummy'."
        )

    def _create_llm_core(self, backend: str, base_url: str | None) -> LLMCore:
        """Creates the concrete LLM core implementation based on the backend."""

        if backend == "dummy":
            return DummyLLMCore()

        if backend == "ollama":
            if not base_url:
                raise KeyError(
                    "core.ollama_url must be set when core.backend is configured as 'ollama'."
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
                        "The Ollama backend is enabled (core.backend: 'ollama'), "
                        "but the Python package 'ollama' is not installed. "
                        "Install it with 'pip install ollama' or set core.backend to 'dummy'."
                    ) from exc
                raise

            return ollama_core_cls(base_url=base_url)

        raise ValueError(f"Unsupported backend: {backend!r}")

    def _load_ollama_core_class(self) -> type[LLMCore]:
        """Isolated import to encapsulate the optional dependency cleanly."""

        from core.ollama_llm_core import OllamaLLMCore

        return OllamaLLMCore

    def _build_guard(self, sec_cfg: dict | None) -> BasicGuard | None:
        if not isinstance(sec_cfg, dict):
            return None

        enabled = bool(sec_cfg.get("enabled", True))
        if not enabled:
            return None

        raw_guard_name = sec_cfg.get("guard", "BasicGuard")
        guard_name = (
            "BasicGuard" if raw_guard_name is None else str(raw_guard_name).strip()
        )
        if not guard_name:
            guard_name = "BasicGuard"

        guard_settings = dict(sec_cfg)
        guard_settings["enabled"] = enabled

        try:
            return create_guard(guard_name, guard_settings)
        except ValueError as exc:
            raise ValueError(
                f"Unknown security guard in security.guard: {raw_guard_name!r}"
            ) from exc

    def get_api_provider(self):
        """Only build when enabled in YAML. No server start here."""
        if self._api_provider is None:
            if not bool(self._cfg.api["enabled"]):
                return None
            from api.provider import AiApiProvider

            self._api_provider = AiApiProvider(
                keyword_finder=self.get_keyword_finder(),
                wiki_mode=self._cfg.wiki["mode"],
                wiki_proxy_port=int(self._cfg.wiki["proxy_port"]),
                wiki_snippet_limit=int(self._cfg.wiki["snippet_limit"]),
                max_wiki_snippets=int(self._cfg.wiki["max_wiki_snippets"]),
                wiki_timeout=(
                    float(self._cfg.wiki["timeout_connect"]),
                    float(self._cfg.wiki["timeout_read"]),
                ),
                factory=self,
            )
        return self._api_provider

    def get_ui(self):
        """
        Builds TerminalUI or WebUI—without starting it.
        Important: no default for web_port → access directly from YAML.
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
                self,
                self._cfg,
                finder,
                int(wiki["snippet_limit"]),
                int(wiki["max_wiki_snippets"]),
                wiki["mode"],
                int(wiki["proxy_port"]),
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
                self,
                self._cfg,
                finder,
                int(wiki["snippet_limit"]),
                int(wiki["max_wiki_snippets"]),
                wiki["mode"],
                int(wiki["proxy_port"]),
                web_host=host,
                web_port=port,
                wiki_timeout=(
                    float(wiki["timeout_connect"]),
                    float(wiki["timeout_read"]),
                ),
            )
        else:
            raise ValueError(
                f"Unknown UI type: {ui_type!r} (expected 'web' or 'terminal')"
            )

        return self._ui
