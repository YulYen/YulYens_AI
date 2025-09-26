# src/config/config_singleton.py
from __future__ import annotations

from pathlib import Path

import yaml

from .texts import Texts

class Config:
    _instance: 'Config | None' = None

    def __new__(cls, path: str = "config.yaml"):
        # Singleton-Instanz erzeugen, falls noch nicht vorhanden
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(path)
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """
        Setzt die Singleton-Instanz zurück.
        Nur in Tests verwenden, um eine neue Config aus einem anderen Pfad zu laden.
        """
        cls._instance = None

    def _load_config(self, path: str) -> None:
        """Lädt die YAML-Datei, Texte und speichert die Daten als Attribute."""
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

        if not isinstance(data, dict):
            raise ValueError(f"Configuration file '{config_path}' must contain a mapping of settings.")

        try:
            language = data.pop("language")
        except KeyError as exc:
            raise KeyError(f"Configuration file '{config_path}' is missing required key 'language'.") from exc

        if not isinstance(language, str) or not language.strip():
            raise ValueError("Config value 'language' must be a non-empty string like 'de' or 'en'.")

        self.language = language
        locales_dir = config_path.parent / "locales"
        text_catalog = Texts(language=language, locales_dir=locales_dir)
        self.texts = text_catalog
        self.t = text_catalog.format

        # Jede weitere Top-Level-Sektion (core, ui, wiki, logging, api, security, ...)
        # als Attribut speichern.
        for section, settings in data.items():
            setattr(self, section, settings)

    def override(self, section: str, updates: dict) -> None:
        """
        Aktualisiert Konfigurationsschlüssel im angegebenen Abschnitt.
        Nur für Tests gedacht, damit man einzelne Parameter anpassen kann, ohne
        die ganze YAML zu verändern.
        """
        if hasattr(self, section):
            section_dict = getattr(self, section)
            if isinstance(section_dict, dict):
                section_dict.update(updates)
            else:
                # Text-Kataloge implementieren eine Mapping-Schnittstelle.
                try:
                    section_dict.update(updates)
                except AttributeError as exc:
                    raise TypeError(f"Section '{section}' does not support updates.") from exc