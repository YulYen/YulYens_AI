import pytest

from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider


def test_dummy_llm_core_echoes_input() -> None:
    """Der DummyLLMCore soll den letzten User‑Input deterministisch spiegeln."""
    llm = DummyLLMCore()
    messages = [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": "Hallo Welt"},
    ]
    chunks = list(llm.stream_chat(model_name="any", messages=messages))
    assert len(chunks) == 1
    assert chunks[0]["message"]["content"] == "ECHO: Hallo Welt"


def test_streaming_provider_with_dummy_llm() -> None:
    """Der StreamingProvider soll mit einem injizierten DummyLLMCore funktionieren."""
    llm = DummyLLMCore()
    provider = YulYenStreamingProvider(
        base_url="http://dummy",  # wird vom Dummy ignoriert
        persona="TEST",
        persona_prompt="Dies ist ein System‑Prompt.",
        persona_options={},
        model_name="dummy-model",
        warm_up=False,
        llm_core=llm,
    )
    messages = [
        {"role": "user", "content": "Ping"},
    ]
    # Sammle die Antwort vom Stream
    out = list(provider.stream(messages))
    # Es sollte genau eine Chunkantwort geben, die den Echo enthält (ohne Leerzeichen)
    assert len(out) == 1
    assert "ECHO: Ping" in out[0]