# tests/test_config.py
import importlib
from datetime import datetime

import pytest
from config.config_singleton import Config
from config.personas import _load_system_prompts
from core import utils as utils_module
from core.dummy_llm_core import DummyLLMCore
from core.factory import AppFactory
from core.streaming_provider import YulYenStreamingProvider
from core.utils import (
    _greeting_text,
    _system_prompt_with_date,
    _wiki_mode_enabled,
)


def test_launch_main_handles_missing_config(tmp_path, monkeypatch, capfd):
    from src import launch

    Config.reset_instance()
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        launch.main()

    assert excinfo.value.code != 0

    captured = capfd.readouterr()
    expected_path = tmp_path / "config.yaml"
    assert "Configuration file" in captured.err
    assert str(expected_path) in captured.err

    Config.reset_instance()


def _build_test_cfg(backend: str = "dummy", core_updates: dict | None = None):
    class DummyCfg:
        def __init__(self) -> None:
            self.core = {
                "backend": backend,
                "ollama_url": "http://127.0.0.1:11434",
                "model_name": "leo-hessianai-13b-chat.Q5",
                "include_date": False,
                "warm_up": False,
            }
            self.api = {"enabled": False}
            self.ui = {"type": None}
            self.wiki = {
                "mode": "offline",
                "proxy_port": 12345,
                "snippet_limit": 250,
                "timeout_connect": 0.1,
                "timeout_read": 0.1,
            }
            self.logging = {"conversation_prefix": "test_conv"}

    cfg = DummyCfg()
    if core_updates:
        cfg.core.update(core_updates)
    cfg.core["backend"] = backend
    return cfg


def _prepare_factory(
    monkeypatch, backend: str = "dummy", core_updates: dict | None = None
):
    cfg = _build_test_cfg(backend, core_updates)

    from config import config_singleton

    monkeypatch.setattr(config_singleton, "Config", lambda: cfg)

    import core.factory as factory_module

    monkeypatch.setattr(factory_module, "Config", lambda: cfg)

    from core import utils

    monkeypatch.setattr(
        utils,
        "_system_prompt_with_date",
        lambda name, include: f"SYSTEM::{name}",
    )

    import config.personas as personas

    monkeypatch.setattr(personas, "get_options", lambda name: {"temperature": 0.1})

    return cfg


def test_factory_builds_streamer_with_dummy_core(monkeypatch):
    cfg = _prepare_factory(monkeypatch, backend="dummy")

    fac = AppFactory()
    streamer = fac.get_streamer_for_persona("DORIS")

    assert isinstance(streamer, YulYenStreamingProvider)
    assert streamer.model_name == cfg.core["model_name"]
    assert streamer.persona == "DORIS"
    assert streamer.persona_options == {"temperature": 0.1}
    assert isinstance(streamer._llm_core, DummyLLMCore)


def test_factory_builds_streamer_with_ollama_core(monkeypatch):
    cfg = _prepare_factory(monkeypatch, backend="ollama")

    class FakeOllamaCore(DummyLLMCore):
        def __init__(self, base_url: str) -> None:
            self.base_url = base_url

    monkeypatch.setattr(
        AppFactory, "_load_ollama_core_class", lambda self: FakeOllamaCore
    )

    fac = AppFactory()
    streamer = fac.get_streamer_for_persona("DORIS")

    assert isinstance(streamer, YulYenStreamingProvider)
    assert isinstance(streamer._llm_core, FakeOllamaCore)
    assert streamer._llm_core.base_url == cfg.core["ollama_url"]


def test_factory_ollama_backend_missing_dependency(monkeypatch):
    _prepare_factory(monkeypatch, backend="ollama")

    def broken_loader(self):
        raise ModuleNotFoundError("No module named 'ollama'", name="ollama")

    monkeypatch.setattr(AppFactory, "_load_ollama_core_class", broken_loader)

    fac = AppFactory()

    with pytest.raises(RuntimeError) as excinfo:
        fac.get_streamer_for_persona("DORIS")

    message = str(excinfo.value)
    assert "core.backend" in message
    assert "pip install ollama" in message


def _opts(name: str):
    personas = importlib.import_module("config.personas")
    return personas.get_options(name)


def test_peter_has_seed_42():
    opts = _opts("PETER")
    assert isinstance(opts, dict)
    assert opts.get("seed") == 42


def test_others_have_no_seed_by_default():
    for name in ("LEAH", "DORIS", "POPCORN"):
        opts = _opts(name)
        if opts is None:
            continue
        assert "seed" not in opts


def test_greeting_replaces_placeholders(tmp_path):
    """
    Verifies the one-to-one placeholder substitution from YAML:
    - {model_name} -> core.model_name
    - {persona_name} -> _load_system_prompts[0].name
    - unknown placeholders remain unchanged (SafeDict)
    """
    persona_name = _load_system_prompts[0]["name"]
    g = _greeting_text(Config(), persona_name)
    assert f"{persona_name}" in g
    assert "Chat" in g


@pytest.mark.parametrize(
    "mode, expected",
    [
        ("offline", True),
        ("false", False),
        ("online", True),
        (False, False),  # falls mal bool in YAML verwendet wird
        (None, False),
    ],
)
def test_wiki_mode_enabled(mode, expected):
    """
    Current behavior: KeywordFinder active only for 'offline' and 'online'.
    Everything else (false/None) → off.
    """
    assert _wiki_mode_enabled(mode) is expected


def test_system_prompt_with_date_uses_localized_suffix(monkeypatch):
    class _FixedDatetime(datetime):
        @classmethod
        def now(cls):
            return cls(2024, 1, 2)

    Config.reset_instance()
    cfg = Config()
    persona_name = _load_system_prompts[0]["name"]

    monkeypatch.setattr(utils_module, "get_prompt_by_name", lambda name: "BASE")
    monkeypatch.setattr(utils_module, "datetime", _FixedDatetime)

    try:
        result = _system_prompt_with_date(persona_name, True)
        expected_suffix = cfg.t("persona_prompt_date_suffix", date="2024-01-02")
        assert result == f"BASE | {expected_suffix}"
    finally:
        Config.reset_instance()
