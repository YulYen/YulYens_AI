from core.dummy_llm_core import DummyLLMCore
from core.orchestrator import broadcast_to_ensemble
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
