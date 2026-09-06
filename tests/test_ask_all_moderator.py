"""Das Fazit über eine Ask-All-Runde (#27)."""

from __future__ import annotations

import threading

import pytest
from config.config_singleton import Config
from config.personas import quietest_persona_name
from core.ask_all_moderator import (
    MODERATOR_PERSONA,
    build_messages,
    iter_verdict,
    moderator_options,
    reply_char_budget,
    usable_replies,
)
from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider

from tests.doubles import streamer_double


class _RecordingFactory:
    """Merkt sich, womit der Moderator-Streamer gebaut wurde."""

    def __init__(self, streamer=None):
        self.calls: list[tuple[str, str, dict]] = []
        self._streamer = streamer

    def get_streamer_for_guest(self, name, prompt, options=None):
        self.calls.append((name, prompt, dict(options or {})))
        if self._streamer is not None:
            return self._streamer
        return YulYenStreamingProvider(
            base_url="",
            persona=name,
            persona_prompt=prompt,
            persona_options={},
            model_name="dummy",
            llm_core=DummyLLMCore(),
        )


def _token_stream(*tokens: str):
    """Ein Generator als `stream()`-Ersatz — Listen haben kein `close()`."""

    def _stream(*_args, **_kwargs):
        yield from tokens

    return _stream


# ---- Was überhaupt eine Antwort ist ----------------------------------------


def test_a_placeholder_is_not_an_answer():
    """„…" steht in noch laufenden Sektionen — ein Fazit darüber wäre Unsinn."""
    assert usable_replies({"LEAH": "…", "DORIS": "  ", "PETER": " Ja. "}) == {
        "PETER": "Ja."
    }


def test_a_single_answer_gets_no_verdict_and_costs_no_model_run():
    """Unter zwei Antworten gibt es nichts zu moderieren — und nichts zu zahlen."""
    factory = _RecordingFactory()

    assert list(iter_verdict(factory, "Frage?", {"LEAH": "A", "DORIS": "…"})) == []
    assert factory.calls == []


# ---- Der Prompt -------------------------------------------------------------


def test_the_answers_travel_as_exactly_one_user_message():
    """Genau eine user-Nachricht — sonst sieht der Eingangs-Guard sie nicht.

    `stream()` prüft die *letzte* user-Nachricht. Zwei Nachrichten daraus zu
    machen hieße, die Antworten still an der Prüfung vorbeizuführen.
    """
    messages = build_messages("Frage?", {"LEAH": "A", "DORIS": "B"}, num_ctx=8192)

    assert [m["role"] for m in messages] == ["user"]
    assert "### LEAH" in messages[0]["content"]
    assert "Frage?" in messages[0]["content"]


def test_a_long_answer_is_trimmed_and_says_so():
    """Ohne Marker liest der Moderator einen abgeschnittenen Satz als ganzen."""
    budget = reply_char_budget(2, 8192)
    marker = Config().t("ask_all_moderator_truncated")

    content = build_messages(
        "Frage?", {"LEAH": "x" * (budget + 500), "DORIS": "kurz"}, num_ctx=8192
    )[0]["content"]

    assert content.count("x") == budget
    assert marker.strip() in content


def test_the_budget_shrinks_with_more_answers_and_a_smaller_window():
    """Das Budget kommt aus dem Kontextfenster, nicht aus einer runden Zahl."""
    assert reply_char_budget(2, 8192) > reply_char_budget(4, 8192)
    assert reply_char_budget(4, 4096) < reply_char_budget(4, 8192)


def test_even_a_tiny_window_leaves_more_than_a_sentence_fragment():
    """Sonst bekommt der Moderator vier Wortfetzen statt vier Antworten."""
    assert reply_char_budget(4, 512) >= 200


# ---- Der Lauf selbst --------------------------------------------------------


def test_the_verdict_streams_token_by_token_and_ends_with_the_whole_text():
    factory = _RecordingFactory()

    events = list(iter_verdict(factory, "Frage?", {"LEAH": "A", "DORIS": "B"}))

    assert events[-1] == {
        "type": "done",
        "reply": "".join(e["token"] for e in events[:-1]).strip(),
    }
    assert events[-1]["reply"]
    assert all(e["type"] == "token" for e in events[:-1])


def test_the_moderator_borrows_the_quietest_personas_options():
    """Zusammenfassen ist keine kreative Aufgabe — also die niedrigste Temperatur.

    Abgeleitet statt verdrahtet, damit die Wahl auch für ein fremdes Ensemble
    stimmt; im Ensemble `classic` ist das PETER.
    """
    factory = _RecordingFactory()

    list(iter_verdict(factory, "Frage?", {"LEAH": "A", "DORIS": "B"}))

    name, prompt, options = factory.calls[0]
    assert name == MODERATOR_PERSONA
    assert prompt == Config().t("ask_all_moderator_system")
    assert options == moderator_options()
    assert quietest_persona_name() == "PETER"


def test_the_verdict_is_never_written_to_the_store():
    """Ask-All zeichnet nicht auf — ein Fazit über vier Fäden erst recht nicht."""
    double = streamer_double()
    double.stream.side_effect = _token_stream("Fa", "zit")
    factory = _RecordingFactory(streamer=double)

    list(iter_verdict(factory, "Frage?", {"LEAH": "A", "DORIS": "B"}))

    double.set_conversation.assert_not_called()
    double.record_conversation.assert_not_called()


def test_the_kill_switch_stops_the_verdict_mid_stream():
    """„Neues Gespräch" darf keinen Modelllauf im Hintergrund weiterlaufen lassen."""
    stop = threading.Event()
    double = streamer_double()
    double.stream.side_effect = _token_stream(*"abcdefghij")
    factory = _RecordingFactory(streamer=double)

    seen = []
    for event in iter_verdict(
        factory, "Frage?", {"LEAH": "A", "DORIS": "B"}, stop_event=stop
    ):
        if event["type"] == "token":
            seen.append(event["token"])
            stop.set()

    assert seen == ["a"]


def test_only_sampling_is_inherited_from_the_persona(monkeypatch):
    """Ein fremdes Ensemble darf die *Form* des Fazits nicht bestimmen.

    `format` machte daraus JSON, `stop` schnitte es ab, `num_predict` beendete
    es nach n Tokens, `system` überschriebe den Moderator-Prompt — und keiner
    der vier Fälle sähe nach einem Fehler aus, weil niemand weiß, wie ein Fazit
    aussehen sollte.
    """
    monkeypatch.setattr(
        "config.personas.get_options",
        lambda name: {
            "temperature": 0.1,
            "num_ctx": 4096,
            "format": "json",
            "stop": ["\n"],
            "num_predict": 20,
            "system": "Du bist wer anders.",
        },
    )

    options = moderator_options()

    assert options == {"temperature": 0.1, "num_ctx": 4096}


def test_a_persona_without_a_temperature_loses_against_one_with(monkeypatch):
    """Ohne Angabe zählt 1.0 — sonst gewänne die Persona, über die nichts bekannt ist."""
    monkeypatch.setattr(
        "config.personas.get_options",
        lambda name: {"temperature": 0.4} if name == "B" else {},
    )

    assert quietest_persona_name(["A", "B", "C"]) == "B"


def test_an_empty_ensemble_is_an_error_not_a_silent_default():
    with pytest.raises(ValueError):
        quietest_persona_name([])
