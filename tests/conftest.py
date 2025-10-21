# tests/conftest.py
import importlib
import socket
from urllib.parse import urlparse

import pytest
from api.app import app, set_provider
from config.config_singleton import Config
from core.factory import AppFactory
from fastapi.testclient import TestClient
from launch import (
    ensure_kiwix_running_if_offlinemode_and_autostart,
    start_wiki_proxy_thread,
)

from tests.util import has_spacy_model


def _should_use_ollama(request, cfg) -> bool:
    marker = request.node.get_closest_marker("ollama")
    if marker is None:
        return False

    backend = str(cfg.core.get("backend", "ollama")).strip().lower()
    if backend != "ollama":
        pytest.skip("Test requires core.backend='ollama'")

    try:
        importlib.import_module("ollama")
    except ModuleNotFoundError:
        pytest.skip("Python package 'ollama' is not installed")

    base_url = cfg.core.get("ollama_url")
    if base_url:
        parsed = urlparse(base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (80 if parsed.scheme == "http" else 443)
        try:
            with socket.create_connection((host, port), timeout=1):
                pass
        except OSError:
            pytest.skip(f"Ollama server at {base_url} is not reachable")

    return True


@pytest.fixture(scope="function")
def client(request):
    # Reset the config singleton and load the test configuration
    Config.reset_instance()
    # Create a dedicated test config or reuse the repository's config.yaml
    cfg = Config("config.yaml")
    use_ollama = _should_use_ollama(request, cfg)
    # Override this test runtime flag
    core_updates = {"include_date": False}
    if not use_ollama:
        core_updates["backend"] = "dummy"
    cfg.override("core", core_updates)
    cfg.override("wiki", {"mode": False})
    # Build the provider from the factory and inject it
    factory = AppFactory()
    set_provider(factory.get_api_provider())
    # Provide the TestClient
    client = TestClient(app)
    yield client
    # Cleanup: reset the provider and clear the config
    set_provider(None)
    Config.reset_instance()


@pytest.fixture(scope="function")
def client_with_date_and_wiki(request):
    if not has_spacy_model("de_core_news_lg"):
        pytest.skip("spaCy model de_core_news_lg not installed")
    # Reset the config singleton and load the test configuration
    Config.reset_instance()
    cfg = Config("config.yaml")

    use_ollama = _should_use_ollama(request, cfg)
    if not use_ollama:
        cfg.override("core", {"backend": "dummy"})

    # Start the wiki proxy
    start_wiki_proxy_thread()
    ensure_kiwix_running_if_offlinemode_and_autostart(cfg)

    # Build the provider from the factory and inject it
    factory = AppFactory()
    set_provider(factory.get_api_provider())

    # Provide the TestClient
    client = TestClient(app)
    yield client
    # Cleanup: reset the provider and clear the config
    set_provider(None)
    Config.reset_instance()
