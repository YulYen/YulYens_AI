# tests/conftest.py
import importlib
import socket
import sys
import types
from urllib.parse import urlparse

import pytest


# ---------------------------------------------------------------------------
# Optional dependency fallbacks
# ---------------------------------------------------------------------------
try:
    import huggingface_hub as _huggingface_hub  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - executed only in CI without the dep
    _huggingface_hub = types.ModuleType("huggingface_hub")
    sys.modules["huggingface_hub"] = _huggingface_hub


if not hasattr(_huggingface_hub, "HfFolder"):
    class _FallbackHfFolder:
        """Minimal stub used when the real class is unavailable."""

        _token: str | None = None

        @classmethod
        def save_token(cls, token: str) -> None:
            cls._token = token

        @classmethod
        def get_token(cls) -> str | None:
            return cls._token

        @classmethod
        def token_exists(cls) -> bool:
            return cls._token is not None


    _huggingface_hub.HfFolder = _FallbackHfFolder  # type: ignore[attr-defined]


if not hasattr(_huggingface_hub, "whoami"):
    def _fallback_whoami(*_args, **_kwargs):  # pragma: no cover - trivial stub
        return {"name": "stub-user"}


    _huggingface_hub.whoami = _fallback_whoami  # type: ignore[attr-defined]


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
    cfg.ensemble = "classic"
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
    cfg.ensemble = "classic"

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


@pytest.fixture(autouse=True)
def _default_ensemble(monkeypatch):
    """Ensure the classic persona ensemble is available in tests."""

    original_load_config = Config._load_config

    def _patched_load_config(self, path):
        original_load_config(self, path)
        if getattr(self, "ensemble", None) is None:
            self.ensemble = "classic"

    monkeypatch.setattr(Config, "_load_config", _patched_load_config)
    yield

