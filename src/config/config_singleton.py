"""Singleton-backed configuration loader used throughout the application."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from .schema import validate_config
from .texts import Texts


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into ``base`` (override wins). Mutates base."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class Config:
    # Die YAML-Sektionen landen per setattr auf der Instanz (siehe
    # _load_config). Ohne diese Deklarationen sieht ein Typprüfer sie nicht —
    # sie sind reine Annotationen, zur Laufzeit entsteht hier nichts (#52).
    # Fehlt eine Sektion in der YAML, existiert das Attribut nicht; Aufrufer
    # nutzen dafür wie bisher `getattr(cfg, "stt", {})`.
    api: dict[str, Any]
    briefing: dict[str, Any]
    context_management: dict[str, Any]
    core: dict[str, Any]
    email_adapter: dict[str, Any]
    evals: dict[str, Any]
    logging: dict[str, Any]
    security: dict[str, Any]
    stt: dict[str, Any]
    tts: dict[str, Any]
    ui: dict[str, Any]
    wiki: dict[str, Any]

    _instance: Config | None = None

    def __new__(cls, path: str = "config.yaml"):
        # Create the singleton instance on first access
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(path)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        Resets the singleton instance.
        Use only in tests to load a new config from another path.
        """
        cls._instance = None

    def _load_config(self, path: str) -> None:
        """Loads the YAML file, texts, and stores the data as attributes."""
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        if not isinstance(data, dict):
            raise ValueError(
                f"Configuration file '{config_path}' must contain a mapping of settings."
            )

        # Optional local override (gitignored): keep personal/secret values
        # (e.g. real mail host/address) out of the tracked config.yaml.
        # Tests set YULYEN_SKIP_LOCAL_CONFIG=1 so a developer's personal
        # config.local.yaml cannot change test behavior vs. CI.
        if not os.environ.get("YULYEN_SKIP_LOCAL_CONFIG"):
            local_path = config_path.with_name("config.local.yaml")
            if local_path.is_file():
                with local_path.open("r", encoding="utf-8") as fh:
                    local_data = yaml.safe_load(fh) or {}
                if isinstance(local_data, dict):
                    _deep_merge(data, local_data)

        try:
            language = data.pop("language")
        except KeyError as exc:
            raise KeyError(
                f"Configuration file '{config_path}' is missing required key 'language'."
            ) from exc

        if not isinstance(language, str) or not language.strip():
            raise ValueError(
                "Config value 'language' must be a non-empty string like 'de' or 'en'."
            )

        _rename_briefing_to_rss(data)

        # Schema-Prüfung (#43): beim Start bewusst nur eine Warnung. Ein
        # laufendes Setup darf nicht an einem Schema scheitern, das die
        # persönliche config.local.yaml nie gesehen hat — hart wird es erst in
        # `--doctor` und /healthz.
        for problem in validate_config(
            {**data, "language": language}, source=str(config_path)
        ):
            logging.warning("[CONFIG] %s", problem)

        self.language = language
        # Anchor on the project root, independent of the config file location
        project_root = Path(__file__).resolve().parents[2]  # .../repo-root
        locales_dir = project_root / "locales"
        text_catalog = Texts(language=language, locales_dir=locales_dir)
        self.texts = text_catalog
        self.t = text_catalog.format

        # Store every remaining top-level section (core, ui, wiki, logging, api, security, ...)
        # as an attribute on the configuration instance.
        for section, settings in data.items():
            setattr(self, section, settings)

        # Persona ensembles are selected at runtime (e.g., via CLI parameter).
        # Ensure the attribute exists even before it is set explicitly — an
        # `ensemble:` key in the YAML is kept as documented fallback for `-e`.
        self.ensemble: str | None = getattr(self, "ensemble", None)

    def override(self, section: str, updates: dict) -> None:
        """
        Updates configuration keys in the given section.
        Intended for tests so individual parameters can be adjusted without
        changing the entire YAML.
        """
        if hasattr(self, section):
            section_dict = getattr(self, section)
            if isinstance(section_dict, dict):
                section_dict.update(updates)
            else:
                # Text catalogs implement a mapping interface.
                try:
                    section_dict.update(updates)
                except AttributeError as exc:
                    raise TypeError(
                        f"Section '{section}' does not support updates."
                    ) from exc


def _rename_briefing_to_rss(data: dict) -> None:
    """`briefing:` heisst seit #73 `rss:` — die alte Sektion wird weitergelesen.

    Umbenennen ohne Alias waere ein stiller Bruch: die rekursive Schema-Pruefung
    (#66) meldete jedem Bestandsnutzer „unbekannte Sektion 'briefing'", und die
    Feeds waeren einfach weg — ohne dass irgendwo steht, warum. Derselbe Weg wie
    bei `ui.web.share_auth` -> `ui.web.auth`: lesen, warnen, nicht brechen.

    Steht beides da, gewinnt `rss:` — der neue Name ist die Absicht.
    """
    legacy = data.pop("briefing", None)
    if legacy is None:
        return
    logging.warning(
        "[CONFIG] Die Sektion 'briefing:' heisst jetzt 'rss:' — bitte in der "
        "config.yaml umbenennen. Sie wird vorerst weiter gelesen."
    )
    if not isinstance(legacy, dict):
        return
    current = data.get("rss")
    data["rss"] = {**legacy, **current} if isinstance(current, dict) else legacy
