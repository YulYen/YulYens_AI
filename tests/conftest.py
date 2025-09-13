# tests/conftest.py
import pytest
from fastapi.testclient import TestClient
from config.config_singleton import Config
from api.app import app, set_provider
from core.factory import AppFactory
from launch import  start_wiki_proxy_thread, ensure_kiwix_running_if_offlinemode_and_autostart
from tests.util import has_spacy_model

@pytest.fixture(scope="function")
def client():
    # Config-Singleton zurücksetzen und Test-Config laden
    Config.reset_instance()
    # eigene Test-Config erzeugen oder vorhandene tests/config.yaml laden
    cfg = Config("config.yaml")
    # Schalter für dieses Test-Laufzeit-Flag überschreiben
    cfg.override("core", {"include_date": False})
    cfg.override("wiki", {"mode": False})
    # Provider aus Factory erstellen und injizieren
    factory = AppFactory()
    set_provider(factory.get_api_provider())
    # TestClient bereitstellen
    client = TestClient(app)
    yield client
    # Aufräumen: Provider zurücksetzen und Config löschen
    set_provider(None)
    Config.reset_instance()

@pytest.fixture(scope="function")
def client_with_date_and_wiki():
    if not has_spacy_model("de_core_news_lg"):
        pytest.skip("spaCy model de_core_news_lg not installed")
    # Config-Singleton zurücksetzen und Test-Config laden
    Config.reset_instance()
    cfg = Config("config.yaml")

    # Wiki starten
    start_wiki_proxy_thread()
    ensure_kiwix_running_if_offlinemode_and_autostart(cfg)

    # Provider aus Factory erstellen und injizieren
    factory = AppFactory()
    set_provider(factory.get_api_provider())

    # TestClient bereitstellen
    client = TestClient(app)
    yield client
    # Aufräumen: Provider zurücksetzen und Config löschen
    set_provider(None)
    Config.reset_instance()