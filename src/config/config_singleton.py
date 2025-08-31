# src/config/config_singleton.py
import yaml

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

    def _load_config(self, path: str):
        """Lädt die YAML-Datei und speichert die Daten als Attribute."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # Jede Top-Level-Sektion (core, ui, wiki, logging, api) als Attribut speichern:
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
            section_dict.update(updates)