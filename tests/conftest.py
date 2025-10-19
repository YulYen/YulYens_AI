# tests/conftest.py
import importlib
import socket
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from config.config_singleton import Config
from api.app import app, set_provider
from core.factory import AppFactory
from launch import start_wiki_proxy_thread, ensure_kiwix_running_if_offlinemode_and_autostart
from tests.util import has_spacy_model


def _should_use_ollama(request, cfg) -> bool:
    marker = request.node.get_closest_marker("ollama")
    if marker is None:
        return False

    backend = str(cfg.core.get("backend", "ollama")).strip().lower()
    if backend != "ollama":
        pytest.skip("Test benötigt core.backend='ollama'")

    try:
        importlib.import_module("ollama")
    except ModuleNotFoundError:
        pytest.skip("Python-Paket 'ollama' nicht installiert")

    base_url = cfg.core.get("ollama_url")
    if base_url:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (80 if parsed.scheme == "http" else 443)
        try:
            with socket.create_connection((host, port), timeout=1):
                pass
        except OSError:
            pytest.skip(f"Ollama-Server unter {base_url} nicht erreichbar")

    return True

@pytest.fixture(scope="function")
def client(request):
    # Config-Singleton zurücksetzen und Test-Config laden
    Config.reset_instance()
    # eigene Test-Config erzeugen oder vorhandene config.yaml aus dem Projektstamm laden
    cfg = Config("config.yaml")
    use_ollama = _should_use_ollama(request, cfg)
    # Schalter für dieses Test-Laufzeit-Flag überschreiben
    core_updates = {"include_date": False}
    if not use_ollama:
        core_updates["backend"] = "dummy"
    cfg.override("core", core_updates)
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
def client_with_date_and_wiki(request):
    if not has_spacy_model("de_core_news_lg"):
        pytest.skip("spaCy model de_core_news_lg not installed")
    # Config-Singleton zurücksetzen und Test-Config laden
    Config.reset_instance()
    cfg = Config("config.yaml")

    use_ollama = _should_use_ollama(request, cfg)
    if not use_ollama:
        cfg.override("core", {"backend": "dummy"})

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