import json
import os
from datetime import datetime
from typing import Any

from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider
from security.tinyguard import BasicGuard


class FakeTokenCore:
    """LLM core stub that emits a predefined sequence of tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    def stream_chat(self, **_kwargs: Any):
        for token in self._tokens:
            yield {"message": {"content": token}}

    def warm_up(self, *_args: Any, **_kwargs: Any) -> None:
        pass


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


class RecordingCore(FakeTokenCore):
    """FakeTokenCore that additionally records the stream_chat kwargs."""

    def __init__(self, tokens: list[str]) -> None:
        super().__init__(tokens)
        self.last_kwargs: dict[str, Any] = {}

    def stream_chat(self, **kwargs: Any):
        self.last_kwargs = kwargs
        return super().stream_chat(**kwargs)


def test_stream_forwards_configured_keep_alive() -> None:
    core = RecordingCore(["Hi"])
    provider = create_streaming_provider(llm_core=core, keep_alive=42)

    list(provider.stream([{"role": "user", "content": "Hallo"}]))

    assert core.last_kwargs["keep_alive"] == 42


def test_stream_defaults_keep_alive_to_600() -> None:
    core = RecordingCore(["Hi"])
    provider = create_streaming_provider(llm_core=core)

    list(provider.stream([{"role": "user", "content": "Hallo"}]))

    assert core.last_kwargs["keep_alive"] == 600


def test_streaming_writes_conversation_json_log(tmp_path) -> None:
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


def test_secret_split_across_tokens_is_blocked() -> None:
    """A secret straddling token boundaries must never leak its prefix."""

    guard = BasicGuard(True, True, True, True)
    # "sk-" arrives first, the key body only completes two tokens later.
    core = FakeTokenCore(["Here is the key: sk-", "SECRETTOBLOCK", "123456789", " ok"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "key?"}]))

    assert "sk-" not in out
    assert "SECRETTOBLOCK" not in out
    assert out == guard.texts["security_blocked_keyword"]


def test_email_split_across_tokens_is_masked() -> None:
    """An email split across token boundaries must be fully masked."""

    guard = BasicGuard(True, True, True, True)
    core = FakeTokenCore(["Contact: max.mustermann", "@example", ".org please"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "mail?"}]))

    assert "max.mustermann@example.org" not in out
    assert guard.mask_text in out
    assert out.startswith("Contact: ")


def test_email_after_long_prefix_still_masked() -> None:
    """Even with text beyond the holdback window, a later email is masked."""

    guard = BasicGuard(True, True, True, True)
    padding = "A" * 150
    core = FakeTokenCore(
        [f"{padding} contact ", "max.mustermann", "@example", ".org end"]
    )
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "mail?"}]))

    assert "max.mustermann@example.org" not in out
    assert guard.mask_text in out
    # The safe prefix is still delivered to the user.
    assert padding in out


def test_plain_text_streams_through_with_guard() -> None:
    """Benign multi-token output is delivered unchanged."""

    guard = BasicGuard(True, True, True, True)
    core = FakeTokenCore(["Hello ", "there, ", "how are ", "you?"])
    provider = create_streaming_provider(llm_core=core, guard=guard)

    out = "".join(provider.stream([{"role": "user", "content": "hi"}]))

    assert out == "Hello there, how are you?"
