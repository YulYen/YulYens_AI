import json
import os
from datetime import datetime
from typing import Any

from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider


class AllowAllGuard:
    """Minimal guard that allows every input and output."""

    def check_input(self, text: str) -> dict[str, Any]:
        return {"ok": True}

    def process_output(self, text: str) -> dict[str, Any]:
        return {"blocked": False, "text": text}

    def check_output(self, text: str) -> dict[str, Any]:
        return {"ok": True}


def create_streaming_provider(
    *, llm_core: DummyLLMCore | None = None, **overrides: Any
) -> YulYenStreamingProvider:
    """Helper to construct consistently configured provider instances."""

    params: dict[str, Any] = {
        "base_url": "http://dummy",
        "persona": "TEST",
        "persona_prompt": "Dies ist ein System-Prompt.",
        "persona_options": {},
        "model_name": "dummy-model",
        "warm_up": False,
    }
    params.update(overrides)

    if llm_core is not None:
        params["llm_core"] = llm_core
    else:
        params["llm_core"] = DummyLLMCore()

    return YulYenStreamingProvider(**params)


def test_dummy_llm_core_echoes_input() -> None:
    """The DummyLLMCore should deterministically echo the latest user input."""

    llm = DummyLLMCore()
    messages = [
        {"role": "system", "content": "ignored"},
        {"role": "user", "content": "Hallo Welt"},
    ]

    chunks = list(llm.stream_chat(model_name="any", messages=messages))

    assert len(chunks) == 1
    assert chunks[0]["message"]["content"] == "ECHO: Hallo Welt"


def test_streaming_provider_with_dummy_llm() -> None:
    """The StreamingProvider should work with an injected DummyLLMCore."""

    llm = DummyLLMCore()
    provider = create_streaming_provider(llm_core=llm)

    messages = [{"role": "user", "content": "Ping"}]
    out = list(provider.stream(messages))

    assert len(out) == 1
    assert "ECHO: Ping" in out[0]


def test_streaming_writes_conversation_log(tmp_path) -> None:
    log_file = tmp_path / f"conv_{datetime.now().strftime('%H%M%S')}.json"

    core = DummyLLMCore()
    provider = create_streaming_provider(
        llm_core=core,
        model_name="LEAH13B",
        persona="DORIS",
        persona_prompt="Du bist DORIS.",
        persona_options={"temperature": 0.2},
        log_file=log_file.name,
        guard=AllowAllGuard(),
    )

    provider._logs_dir = str(tmp_path)
    provider.conversation_log_path = str(tmp_path / log_file.name)

    messages = [{"role": "user", "content": "Sag etwas Nettes."}]
    out = "".join(list(provider.stream(messages)))

    assert out == "ECHO: Sag etwas Nettes."
    assert os.path.exists(provider.conversation_log_path)

    rows = [
        json.loads(line)
        for line in open(provider.conversation_log_path, encoding="utf-8")
    ]
    roles = [row["role"] for row in rows]

    assert "user" in roles and "assistant" in roles
    assert any(
        row.get("bot") == "DORIS" and row.get("model") == "LEAH13B" for row in rows
    )
