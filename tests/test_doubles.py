"""Die Doubles selbst unter Test (#67).

Ein Double, das an der Wirklichkeit vorbeigeht, lässt Tests grün laufen, die in
Produktion fallen — genau die Klasse Fehler, gegen die eine Suite da ist.
Deshalb wird hier geprüft, dass die Doubles die beiden Driftrichtungen von sich
aus abfangen, statt sich darauf zu verlassen, dass jemand sie nachzieht.
"""

import inspect
from unittest.mock import Mock

import pytest
from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider
from security.tinyguard import BasicGuard

from tests.doubles import factory_double, permissive_guard_double, streamer_double


def _real_streamer() -> YulYenStreamingProvider:
    return YulYenStreamingProvider(
        base_url="",
        persona="TEST",
        persona_prompt="",
        persona_options={},
        model_name="dummy",
        llm_core=DummyLLMCore(),
    )


# ---- Richtung 1: die stille -------------------------------------------------


def test_an_unset_attribute_reads_as_absent_not_as_a_truthy_mock():
    """Der teure Fehler: `getattr(x, "guard", None)` bekam nie None.

    Produktivcode fragt so nach optionalen Mitarbeitern. Ein nacktes Mock
    liefert dort ein wahrheitswertiges Objekt, das gar keine Prüfung ist — der
    Kontext-Filter lief dagegen, und der Test blieb grün, bis tief im Guard ein
    `'Mock' object is not subscriptable` kam.
    """
    nackt = Mock()
    assert getattr(nackt, "guard", None) is not None, "so war es vorher"

    assert getattr(streamer_double(), "guard", None) is None


def test_the_streamer_double_only_answers_what_a_real_streamer_has():
    """Ein Tippfehler im Testnamen soll nicht stumm ein Mock erzeugen."""
    double = streamer_double()

    with pytest.raises(AttributeError):
        double.recrod_conversation  # Dreher in 'record'


# ---- Richtung 2: die laute --------------------------------------------------


@pytest.mark.parametrize(
    "method",
    ["stream", "record_conversation", "set_conversation", "set_user", "set_guard"],
)
def test_new_streamer_methods_are_present_without_nachziehen(method):
    """Alle vier Vorfälle waren „Produktivcode ruft etwas, das Double kennt es nicht".

    Mit einer Spezifikation ist jede Methode des echten Streamers automatisch
    am Double — auch eine, die es beim Schreiben dieses Tests noch nicht gab.
    """
    assert hasattr(streamer_double(), method)
    assert hasattr(_real_streamer(), method)


def _public_methods(cls) -> list[str]:
    """Die öffentlichen Methoden einer Klasse.

    Bewusst über die *Klasse* und nicht über eine Instanz: `guard.texts` etwa
    ist ein Attribut, das zufällig ein `__call__` hat (`config.texts.Texts`).
    Eine Instanz nach „public und aufrufbar" zu durchsuchen zählt so etwas
    fälschlich als Methode mit.
    """
    return sorted(
        name
        for name, member in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    )


def test_the_double_covers_every_public_method_of_the_real_streamer():
    """Die Zusicherung ohne Aufzählung: gar keine Methode darf fehlen."""
    double = streamer_double()

    fehlend = [
        name
        for name in _public_methods(YulYenStreamingProvider)
        if not hasattr(double, name)
    ]

    assert fehlend == []


def test_the_presets_are_attributes_a_real_streamer_actually_has():
    """Die eine Lücke, die `create_autospec` offenlässt.

    Gelesen wird nur, was die Klasse kennt — *gesetzt* werden darf dagegen
    alles (kein `spec_set`), sonst könnte man Instanzattribute wie
    `persona_options` gar nicht vorbelegen. Ein Tippfehler in der Vorbelegung
    bliebe damit stumm, und jeder Test liefe gegen ein Attribut, das es in
    Produktion nicht gibt.
    """
    echt = _real_streamer()

    fehlend = [
        name
        for name in ("guard", "persona_options", "last_stream_stats", "model_name")
        if not hasattr(echt, name)
    ]

    assert fehlend == [], f"Das Double belegt vor, was es nicht gibt: {fehlend}"
    assert streamer_double().last_stream_stats == echt.last_stream_stats


def test_calling_with_a_wrong_signature_is_an_error():
    """Signaturen werden mitgeprüft — ein Aufruf, den es nicht gibt, fällt auf."""
    double = streamer_double()

    with pytest.raises(TypeError):
        double.stream(messages=[], gibtesnicht=1)


# ---- Guard- und Factory-Double ----------------------------------------------


def test_the_guard_double_covers_every_public_method_of_the_real_guard():
    """Ersetzt das handgeschriebene AllowAllGuard, das zweimal aufgelaufen ist."""
    double = permissive_guard_double()

    fehlend = [
        name for name in _public_methods(BasicGuard) if not hasattr(double, name)
    ]

    assert fehlend == []


def test_the_permissive_guard_lets_text_through_unchanged():
    double = permissive_guard_double()

    assert double.check_input("egal")["ok"] is True
    assert double.process_output("Hallo Welt")["text"] == "Hallo Welt"
    assert double.output_match_crossing("Hallo", 2) is None
    # Die einzige Guard-Methode, deren durchlassende Antwort falsy ist (#60a).
    # Ohne Vorbelegung liefert das Mock ein wahrheitswertiges Objekt, und
    # `context_verdict` verwirft dann *jeden* injizierten Kontext — lautlos.
    assert double.check_context_only("egal") is None


def test_the_factory_double_returns_no_guard_by_default():
    """Sonst prüft der Kontext-Filter gegen ein Mock statt gegen einen Guard."""
    assert factory_double().build_guard() is None


def test_the_factory_double_starts_without_login_and_without_store():
    """Die echten Produktionsvorgaben — und beide sind *falsy*.

    Genau da schlägt die stille Richtung zu: ein Mock wäre wahr, die WebUI
    startete im Test mit einer Anmeldung, die es nicht gibt, und über einer
    Ablage, die nichts speichert.
    """
    double = factory_double()

    assert double.get_auth_provider().gradio_auth() is None
    assert double.get_auth_provider().identifies_users is False
    assert double.get_store().records is False
