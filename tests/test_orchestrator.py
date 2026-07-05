from core.dummy_llm_core import DummyLLMCore
from core.orchestrator import broadcast_to_ensemble, iter_broadcast_events
from core.streaming_provider import YulYenStreamingProvider


class _DummyFactory:
    def __init__(self):
        self._cache: dict[str, YulYenStreamingProvider] = {}

    def get_streamer_for_persona(self, persona: str) -> YulYenStreamingProvider:
        if persona not in self._cache:
            self._cache[persona] = YulYenStreamingProvider(
                base_url="",
                persona=persona,
                persona_prompt="",
                persona_options={},
                model_name="dummy",
                llm_core=DummyLLMCore(),
            )
        return self._cache[persona]


def test_broadcast_to_ensemble_collects_dummy_responses():
    factory = _DummyFactory()
    responses = broadcast_to_ensemble(
        factory, "Ping", persona_names=["Alpha", "Beta"], on_token=None
    )

    assert responses == [
        {"persona": "Alpha", "reply": "ECHO: Ping"},
        {"persona": "Beta", "reply": "ECHO: Ping"},
    ]


def test_broadcast_to_ensemble_streams_tokens_in_order():
    factory = _DummyFactory()
    captured: list[tuple[str, str]] = []

    broadcast_to_ensemble(
        factory,
        "Hallo zusammen",
        persona_names=["Gamma", "Delta"],
        on_token=lambda persona, token: captured.append((persona, token)),
    )

    assert captured[0][0] == "Gamma"
    assert captured[-1][0] == "Delta"
    assert all(isinstance(item[1], str) for item in captured)


class _RecordingFactory:
    """Factory whose streamers record the exact messages they receive."""

    def __init__(self):
        self.seen_messages: dict[str, list[dict[str, str]]] = {}

    def get_streamer_for_persona(self, persona: str):
        factory = self

        class _Streamer:
            def stream(self, messages):
                factory.seen_messages[persona] = [m.copy() for m in messages]
                yield f"ECHO: {messages[-1]['content']}"

        return _Streamer()


def test_broadcast_passes_context_messages_before_user_prompt():
    factory = _RecordingFactory()
    context = [
        {"role": "system", "content": "Guardrail"},
        {"role": "system", "content": "WIKI SNIPPET"},
    ]

    responses = broadcast_to_ensemble(
        factory,
        "Ping",
        persona_names=["Alpha", "Beta"],
        context_messages=context,
    )

    assert [r["reply"] for r in responses] == ["ECHO: Ping", "ECHO: Ping"]
    for persona in ("Alpha", "Beta"):
        assert factory.seen_messages[persona] == context + [
            {"role": "user", "content": "Ping"}
        ]


def test_broadcast_without_context_messages_sends_only_user_prompt():
    factory = _RecordingFactory()

    broadcast_to_ensemble(factory, "Ping", persona_names=["Alpha"])

    assert factory.seen_messages["Alpha"] == [{"role": "user", "content": "Ping"}]


def test_iter_broadcast_events_yields_tokens_and_done_per_persona():
    factory = _DummyFactory()
    events = list(
        iter_broadcast_events(factory, "Ping", persona_names=["Alpha", "Beta"])
    )

    # Pro Persona: mindestens ein Token-Event, abgeschlossen mit genau einem done.
    done_events = [e for e in events if e["type"] == "done"]
    assert [e["persona"] for e in done_events] == ["Alpha", "Beta"]
    assert all(e["reply"] == "ECHO: Ping" for e in done_events)

    token_events = [e for e in events if e["type"] == "token"]
    assert token_events, "expected streamed token events"
    # Kumulierter Text wächst monoton und endet im vollen Reply
    alpha_tokens = [e for e in token_events if e["persona"] == "Alpha"]
    assert alpha_tokens[-1]["reply"].strip() == "ECHO: Ping"

    # Reihenfolge: alle Alpha-Events kommen vor dem ersten Beta-Event
    personas_seen = [e["persona"] for e in events]
    assert personas_seen.index("Beta") > personas_seen.index("Alpha")
    assert events[-1] == {"type": "done", "persona": "Beta", "reply": "ECHO: Ping"}
