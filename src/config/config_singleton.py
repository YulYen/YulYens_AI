"""Singleton-backed configuration loader used throughout the application."""
from __future__ import annotations

from pathlib import Path

import yaml

from .texts import Texts


class Config:
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

        self.language = language
        # neu (am Projektsrc ausrichten, unabhängig vom Config-Standort)
        project_root = Path(__file__).resolve().parents[2]   # .../repo-root
        locales_dir = project_root / "locales"
        text_catalog = Texts(language=language, locales_dir=locales_dir)
        self.texts = text_catalog
        self.t = text_catalog.format

        # Store every remaining top-level section (core, ui, wiki, logging, api, security, ...)
        # as an attribute on the configuration instance.
        for section, settings in data.items():
            setattr(self, section, settings)

        # Persona ensembles are selected at runtime (e.g., via CLI parameter).
        # Ensure the attribute exists even before it is set explicitly.
        self.ensemble: str | None = None

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
