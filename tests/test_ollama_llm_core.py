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

from core.ollama_llm_core import OllamaLLMCore


class RecordingClient:
    """Simple fake that records ``chat`` calls."""

    def __init__(self, *, host: str) -> None:
        self.host = host
        self.calls: list[dict[str, object]] = []
        self.return_value: object = object()

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.return_value


@pytest.fixture()
def fake_client_factory(monkeypatch: pytest.MonkeyPatch) -> Callable[[], RecordingClient]:
    """Install a fake :class:`ollama.Client` and return the created instance."""

    created_clients: list[RecordingClient] = []

    def factory(*, host: str) -> RecordingClient:
        client = RecordingClient(host=host)
        created_clients.append(client)
        return client

    monkeypatch.setattr(ollama, "Client", factory)
    monkeypatch.setattr("core.ollama_llm_core.Client", factory)

    def get_last_client() -> RecordingClient:
        assert created_clients, "Client was not instantiated"
        return created_clients[-1]

    return get_last_client


def test_warm_up_uses_dummy_prompt(fake_client_factory: Callable[[], RecordingClient]) -> None:
    core = OllamaLLMCore(base_url="http://example")
    fake_client = fake_client_factory()

    core.warm_up("test-model")

    assert len(fake_client.calls) == 1
    call_kwargs = fake_client.calls[0]
    assert call_kwargs == {
        "model": "test-model",
        "messages": [{"role": "user", "content": "..."}],
    }
    assert "stream" not in call_kwargs


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
    }
    assert call_kwargs["messages"] is messages
    assert call_kwargs["options"] is options
