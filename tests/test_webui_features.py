"""Welche optionalen Funktionen die WebUI anbietet — und warum nicht (#56).

Der Punkt dieses Moduls ist nicht, dass sechs Bools jetzt woanders stehen,
sondern dass drei von ihnen **zweistufig** sind: die Config will es, und
zusätzlich muss etwas da sein. Für genau diese drei gehört „eingeschaltet, aber
nicht verfügbar" gesagt — sonst sucht jemand ein Mikrofon, das nie erscheinen
kann.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from ui.webui_features import WebFeatures


def _cfg(**sections):
    base = {"ui": {}, "storage": {}, "stt": {}, "tts": {}}
    base.update(sections)
    return SimpleNamespace(**base)


class _Store:
    def __init__(self, records: bool) -> None:
        self.records = records


def _detect(cfg, *, records=True, stt=False, piper=False) -> WebFeatures:
    with (
        patch("ui.webui_features.is_stt_available", return_value=stt),
        patch("ui.webui_features.module_available", return_value=piper),
    ):
        return WebFeatures.detect(cfg, _Store(records))


# ---- Die zweite Stufe --------------------------------------------------------


@pytest.mark.parametrize(
    "section,cfg_kwargs,attribute",
    [
        ("stt", {"stt": {"enabled": True}}, "stt"),
        (
            "tts",
            {"tts": {"enabled": True, "features": {"web_read_aloud": True}}},
            "tts_read_aloud",
        ),
    ],
)
def test_a_feature_the_config_wants_stays_off_without_its_package(
    section, cfg_kwargs, attribute
):
    """Die Config allein genügt nicht — das Paket muss installiert sein."""
    features = _detect(_cfg(**cfg_kwargs), stt=False, piper=False)

    assert getattr(features, attribute) is False


def test_the_history_card_follows_the_store_not_the_config():
    """`storage.enabled: true` ist die Absicht, `records` die Wirklichkeit (#72).

    Ohne Anmeldung liefert die Factory einen NullStore — die Config sagt
    trotzdem weiter „an". Wer nur sie liest, blendet eine Karte ein, die sich
    nie füllen kann.
    """
    features = _detect(_cfg(storage={"enabled": True}), records=False)

    assert features.history is False


# ---- Die Meldung -------------------------------------------------------------


def test_wanting_something_unavailable_is_worth_a_word():
    """Alle drei zweistufigen Fälle melden sich — auch der Verlauf.

    Für den Verlauf gab es vorher **keine** Meldung: die Karte verschwand
    einfach. Dass alle drei jetzt dieselbe Form haben, ist der eigentliche
    Gewinn — eine siebte Funktion erbt sie, statt sie neu zu erfinden.
    """
    cfg = _cfg(
        storage={"enabled": True},
        stt={"enabled": True},
        tts={"enabled": True, "features": {"web_read_aloud": True}},
    )
    features = _detect(cfg, records=False, stt=False, piper=False)

    notes = features._notes(stt=True, tts=True, history=True)

    assert len(notes) == 3, notes
    assert any("faster-whisper" in note for note in notes)
    assert any("piper" in note for note in notes)
    assert any("Verlauf-Karte" in note for note in notes)


def test_a_feature_nobody_asked_for_stays_quiet():
    """Die Gegenprobe: eine Meldung, die immer kommt, liest bald niemand mehr."""
    features = _detect(_cfg(), records=False)

    assert features._notes(stt=False, tts=False, history=False) == []


# ---- Der Grund für `frozen` --------------------------------------------------


def test_the_answers_do_not_change_while_the_app_runs():
    """Keine Funktion taucht mitten im Betrieb auf; alles steht beim Start fest.

    `frozen` hält das fest, statt es zu behaupten — und zwingt einen Test, der
    etwas umschalten will, zu `replace()`. Das sagt deutlicher, was gemeint
    ist, als ein nachträglich gesetztes Feld.
    """
    features = _detect(_cfg())

    with pytest.raises(Exception):
        features.stt = True  # type: ignore[misc]
