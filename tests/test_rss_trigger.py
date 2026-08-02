"""Der Trigger-Korpus für #73 — zuerst geschrieben, dann die Logik.

Die Reihenfolge ist der Punkt: mit einer naiven Wortliste
(`neu|aktuell|nachricht|schlagzeile|news|briefing|heute`, irgendeins reicht)
traf die Heuristik **9 der 12 harmlosen Sätze** unten. Erst diese Messung hat
die Regeln entworfen — Plural statt Singular, Phrasen statt Einzelwörtern, ein
Riegel gegen Personenbezug. Danach: 0 Fehlalarme, keine verpasste Frage.

Wer eine Regel ergänzt, ergänzt hier **beide** Richtungen: den Satz, der sie
auslösen soll, und den, der es nicht darf.
"""

import pytest
from rss.trigger import feed_aliases, feeds_for_question

FEEDS = ["tagesschau", "heise online"]


# ---- Nachrichtenfragen: alle Quellen ---------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Was gibt's Neues?",
        "Was gibt es heute Neues?",
        "Gibt es aktuelle Nachrichten?",
        "Was steht heute in den Nachrichten?",
        "Erzähl mir die Schlagzeilen von heute.",
        "Was ist heute in der Welt passiert?",
        "Gib mir bitte ein kurzes Briefing.",
        "Neuigkeiten?",
        "Was gibt's aktuell Wichtiges in den News?",
        "Fasse mir die aktuelle Nachrichtenlage zusammen.",
    ],
)
def test_a_news_question_pulls_every_feed(question):
    assert feeds_for_question(question, FEEDS) == tuple(FEEDS)


# ---- Nach Quelle gefragt: genau diese --------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Was sagt die Tagesschau?", "tagesschau"),
        ("Was meldet die tagesschau gerade?", "tagesschau"),
        ("Steht was Neues bei heise?", "heise online"),
        ("Gibt es was bei heise online?", "heise online"),
    ],
)
def test_a_named_source_pulls_only_that_feed(question, expected):
    """Die Auslöser kommen aus der Config, nicht aus einer Wortliste.

    Wer einen Feed ergänzt, bekommt seinen Namen als Auslöser geschenkt — das
    ist der Grund, diese Richtung überhaupt zu bauen.
    """
    assert feeds_for_question(question, FEEDS) == (expected,)


# ---- Die Gegenprobe: das Teure ---------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        # Small Talk an die Persona — der Fehlalarm, der am meisten weh tut:
        # die Persona finge an, Schlagzeilen aufzusagen.
        "Was gibt's Neues bei dir?",
        "Erzähl mir was Neues aus deinem Leben.",
        "Wie geht es dir heute?",
        "Wie war dein Tag heute?",
        # Zeitwörter allein sagen gar nichts.
        "Ich habe heute Geburtstag.",
        "Was ist neu in Python 3.13?",
        "Was bedeutet 'aktuell' auf Englisch?",
        # Singular ist kein Plural: eine Nachricht ≠ die Nachrichten.
        "Schreib mir bitte eine Nachricht an meinen Chef.",
        "Was ist eigentlich eine Schlagzeile?",
        # Über das Thema reden heißt nicht, es abrufen zu wollen.
        "Erkläre mir, wie RSS technisch funktioniert.",
        "Kannst du mir die Zeitung von gestern erklären?",
        "Erzähl mir eine Geschichte über einen Reporter.",
    ],
)
def test_everyday_sentences_stay_quiet(question):
    assert feeds_for_question(question, FEEDS) == ()


def test_without_configured_feeds_nothing_triggers():
    assert feeds_for_question("Was gibt's Neues?", []) == ()


def test_an_empty_question_triggers_nothing():
    assert feeds_for_question("", FEEDS) == ()
    assert feeds_for_question("   ", FEEDS) == ()


# ---- Namensauflösung --------------------------------------------------------


def test_short_words_in_a_feed_name_are_not_triggers():
    """Sonst hinge „Der Spiegel" an jedem „der" im Satz."""
    aliases = feed_aliases("Der Spiegel")
    assert "der" not in aliases
    assert "spiegel" in aliases
    assert feeds_for_question("Der Hund bellt.", ["Der Spiegel"]) == ()


def test_a_feed_name_is_matched_as_a_whole_word():
    """`heise` darf nicht in `heiser` treffen."""
    assert feeds_for_question("Ich bin heiser.", FEEDS) == ()
