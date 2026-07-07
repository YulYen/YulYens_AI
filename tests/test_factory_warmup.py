"""Tests for the one-time startup warm-up in :class:`AppFactory`."""

from typing import Any

import pytest
from config.config_singleton import Config
from core.factory import AppFactory


class RecordingWarmUpCore:
    """LLM-core stub that records warm_up calls."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, Any]] = []

    def warm_up(self, model_name, options=None, keep_alive=600) -> None:
        self.calls.append(
            {"model_name": model_name, "options": options, "keep_alive": keep_alive}
        )
        if self.fail:
            raise RuntimeError("Ollama down")

    def stream_chat(self, **_kwargs: Any):  # pragma: no cover - interface only
        return iter(())


@pytest.fixture()
def cfg():
    Config.reset_instance()
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    yield cfg
    Config.reset_instance()


def _factory_with_core(cfg, core, monkeypatch) -> AppFactory:
    cfg.override("core", {"backend": "ollama"})
    factory = AppFactory()
    monkeypatch.setattr(factory, "_create_llm_core", lambda backend, base_url: core)
    return factory


def test_warm_up_skips_dummy_backend(cfg, monkeypatch) -> None:
    cfg.override("core", {"backend": "dummy"})
    factory = AppFactory()

    def _fail(*_args: Any) -> None:
        raise AssertionError("LLM core must not be built for the dummy backend")

    monkeypatch.setattr(factory, "_create_llm_core", _fail)
    factory.warm_up_model()


def test_warm_up_passes_real_options_and_keep_alive(cfg, monkeypatch) -> None:
    cfg.override("core", {"keep_alive": 42})
    core = RecordingWarmUpCore()
    factory = _factory_with_core(cfg, core, monkeypatch)

    factory.warm_up_model()

    assert len(core.calls) == 1
    call = core.calls[0]
    assert call["model_name"] == cfg.core["model_name"]
    assert call["keep_alive"] == 42
    # Warm with the biggest persona context (classic: uniformly 8192) and a
    # minimal generation so the dummy request stays cheap.
    assert call["options"] == {"num_predict": 1, "num_ctx": 8192}


def test_warm_up_survives_backend_errors(cfg, monkeypatch) -> None:
    core = RecordingWarmUpCore(fail=True)
    factory = _factory_with_core(cfg, core, monkeypatch)

    factory.warm_up_model()  # must not raise

    assert len(core.calls) == 1


def test_warm_up_survives_core_creation_errors(cfg, monkeypatch) -> None:
    cfg.override("core", {"backend": "ollama"})
    factory = AppFactory()

    def _boom(*_args: Any) -> None:
        raise RuntimeError("ollama package missing")

    monkeypatch.setattr(factory, "_create_llm_core", _boom)
    factory.warm_up_model()  # must not raise


def test_warm_up_runs_only_once(cfg, monkeypatch) -> None:
    core = RecordingWarmUpCore()
    factory = _factory_with_core(cfg, core, monkeypatch)

    factory.warm_up_model()
    factory.warm_up_model()

    assert len(core.calls) == 1
