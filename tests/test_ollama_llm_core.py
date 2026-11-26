"""Tests for :mod:`core.ollama_llm_core`."""

from __future__ import annotations

import sys
import types
from collections.abc import Callable

import pytest

try:  # pragma: no cover - executed only when the dependency is missing.
    import ollama  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback for test environment.
    ollama = types.ModuleType("ollama")
    sys.modules["ollama"] = ollama


class _PlaceholderClient:  # pragma: no cover - replaced by monkeypatch.
    def __init__(self, *args, **kwargs) -> None:  # noqa: D401 - placeholder
        raise RuntimeError("This placeholder should be patched in tests")


# Ensure the module exposes a Client symbol so the import in ``core`` works.
if not hasattr(ollama, "Client"):
    ollama.Client = _PlaceholderClient  # type: ignore[attr-defined]

from yulyen_ai.core.ollama_llm_core import OllamaLLMCore


class RecordingClient:
    """Simple fake that records ``chat`` calls."""

    def __init__(self, *, host: str) -> None:
        self.host = host
        self.calls: list[dict[str, object]] = []
        self.return_value: object = object()

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.return_value


class ShowingClient(RecordingClient):
    """Wie oben, beantwortet aber zusätzlich ``show`` — wie ein echter Server."""

    capabilities: dict[str, list[str]] = {
        "qwen3.8:27b": ["completion", "tools", "thinking"],
        "ministral-3:14b": ["completion", "tools", "vision"],
    }

    def __init__(self, *, host: str) -> None:
        super().__init__(host=host)
        self.shown: list[str] = []

    def show(self, model: str):
        self.shown.append(model)
        return types.SimpleNamespace(capabilities=self.capabilities.get(model, []))


@pytest.fixture()
def showing_core(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("yulyen_ai.core.ollama_llm_core.Client", ShowingClient)
    core = OllamaLLMCore(base_url="http://example")
    return core, core._client


@pytest.fixture()
def fake_client_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[], RecordingClient]:
    """Install a fake :class:`ollama.Client` and return the created instance."""

    created_clients: list[RecordingClient] = []

    def factory(*, host: str) -> RecordingClient:
        client = RecordingClient(host=host)
        created_clients.append(client)
        return client

    monkeypatch.setattr(ollama, "Client", factory)
    monkeypatch.setattr("yulyen_ai.core.ollama_llm_core.Client", factory)

    def get_last_client() -> RecordingClient:
        assert created_clients, "Client was not instantiated"
        return created_clients[-1]

    return get_last_client


def test_warm_up_uses_dummy_prompt(
    fake_client_factory: Callable[[], RecordingClient],
) -> None:
    core = OllamaLLMCore(base_url="http://example")
    fake_client = fake_client_factory()

    core.warm_up("test-model")

    assert len(fake_client.calls) == 1
    call_kwargs = fake_client.calls[0]
    assert call_kwargs == {
        "model": "test-model",
        "keep_alive": 600,
        "messages": [{"role": "user", "content": "..."}],
        "options": {},
        "think": False,
    }
    assert "stream" not in call_kwargs


def test_warm_up_forwards_options_and_keep_alive(
    fake_client_factory: Callable[[], RecordingClient],
) -> None:
    core = OllamaLLMCore(base_url="http://example")
    fake_client = fake_client_factory()
    options = {"num_ctx": 8192, "num_predict": 1}

    core.warm_up("test-model", options=options, keep_alive=-1)

    assert len(fake_client.calls) == 1
    call_kwargs = fake_client.calls[0]
    assert call_kwargs == {
        "model": "test-model",
        "keep_alive": -1,
        "messages": [{"role": "user", "content": "..."}],
        "options": options,
        "think": False,
    }


def test_stream_chat_forwards_all_arguments(
    fake_client_factory: Callable[[], RecordingClient],
) -> None:
    core = OllamaLLMCore(base_url="http://example")
    fake_client = fake_client_factory()
    sentinel = object()
    fake_client.return_value = sentinel

    messages = [{"role": "user", "content": "hi"}]
    options = {"temperature": 0.4, "top_p": 0.9}
    keep_alive = 42

    result = core.stream_chat(
        model_name="stream-model",
        messages=messages,
        options=options,
        keep_alive=keep_alive,
    )

    assert result is sentinel
    assert len(fake_client.calls) == 1
    call_kwargs = fake_client.calls[0]
    assert call_kwargs == {
        "model": "stream-model",
        "keep_alive": keep_alive,
        "messages": messages,
        "options": options,
        "stream": True,
        "think": False,
    }
    assert call_kwargs["messages"] is messages
    assert call_kwargs["options"] is options


# ---- think=False (#78) -----------------------------------------------------
#
# Der Streamer liest nur `message.content`. Ein Reasoning-Modell, das denken
# darf, liefert dort lange nichts — also wird das Denken abgestellt, und zwar
# bei jedem Modell: Was ein Modell über sich meldet, stimmt nicht immer.


@pytest.mark.parametrize(
    "model",
    [
        "qwen3.8:27b",  # meldet „thinking"
        "ministral-3:14b",  # kann nicht denken — der Parameter schadet nicht
        # Meldet „thinking" nicht, denkt aber: der Fall, an dem die alte
        # Abfrage per show() scheiterte (2026-11-15).
        "hf.co/google/gemma-4-26B-A4B-it-qat-q4_0-gguf:latest",
    ],
)
def test_every_model_is_asked_not_to_think(showing_core, model) -> None:
    core, client = showing_core

    core.stream_chat(model, [{"role": "user", "content": "hi"}])
    core.warm_up(model)

    assert [call["think"] for call in client.calls] == [False, False]


def test_the_server_is_not_asked_what_the_model_can(showing_core) -> None:
    """Keine Nachfrage per show(): sie kostete eine Anfrage und log beim QAT-Gemma."""
    core, client = showing_core

    core.stream_chat("qwen3.8:27b", [{"role": "user", "content": "hi"}])

    assert client.shown == []
