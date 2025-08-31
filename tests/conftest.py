# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from config.config_singleton import Config
from api.app import app, set_provider
from core.factory import AppFactory

@pytest.fixture(scope="function")
def client():
    # Config-Singleton zurücksetzen und Test-Config laden
    Config.reset_instance()
    # eigene Test-Config erzeugen oder vorhandene tests/config.yaml laden
    cfg = Config("config.yaml")
    # Schalter für dieses Test-Laufzeit-Flag überschreiben
    cfg.override("core", {"include_date": False})
    # Provider aus Factory erstellen und injizieren
    factory = AppFactory()
    set_provider(factory.get_api_provider())
    # TestClient bereitstellen
    client = TestClient(app)
    yield client
    # Aufräumen: Provider zurücksetzen und Config löschen
    set_provider(None)
    Config.reset_instance()