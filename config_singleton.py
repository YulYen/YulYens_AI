# config_singleton.py
import yaml

class Config:
    _instance = None

    def __new__(cls, path: str = "config.yaml"):
        # Singleton-Instanz erzeugen, falls noch nicht vorhanden
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(path)
        return cls._instance

    def _load_config(self, path: str):
        """Lädt die YAML-Datei und speichert die Daten als Attribute."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # Jede Top-Level-Sektion (core, ui, wiki, logging, api) als Attribut speichern:
        for section, settings in data.items():
            setattr(self, section, settings)