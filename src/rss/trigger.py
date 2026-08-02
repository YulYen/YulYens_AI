"""Wann ist eine Frage eine Nachrichtenfrage? (#73)

Reine Funktionen, kein Netz, kein Modell — deshalb **test-first entstanden**:
erst der Korpus in ``tests/test_rss_trigger.py``, dann diese Regeln, gemessen
an Fehlalarmen. Der erste Entwurf war eine Wortliste
(``neu|aktuell|nachricht|heute|…``, irgendeins reicht) und traf **9 von 12**
harmlosen Sätzen — „Wie geht es dir heute?", „Ich habe heute Geburtstag",
„Was ist neu in Python 3.13?". Die Fassung hier: **0**, bei unveränderter
Trefferzahl auf den 14 echten Nachrichtenfragen.

Drei Entwurfsregeln, die diese Differenz ausmachen:

1. **Der Plural macht die Arbeit.** „Nachrichten" sind Nachrichten, „eine
   Nachricht" ist eine Nachricht an den Chef. „Schlagzeilen" will die
   Schlagzeilen, „eine Schlagzeile" ist eine Wortbedeutungsfrage. Deshalb
   stehen hier nur Pluralformen — das ersetzt eine ganze Klasse von
   Sonderregeln gegen Definitionsfragen, die man sonst gebaut hätte.
2. **Einzelne Zeitwörter lösen nichts aus.** „heute", „aktuell", „neu" stehen
   in jedem zweiten Satz. Sie zählen nur als Teil einer Phrase.
3. **Ein Personenbezug schlägt alles.** „Was gibt's Neues **bei dir**?" ist
   Small Talk an die Persona, keine Bitte um Schlagzeilen — und der Fehlalarm
   wäre teuer: die Persona würde plötzlich Nachrichten aufsagen.

Wer eine Regel ergänzt, legt in den Korpus **den Satz daneben, den sie nicht
treffen darf**. Die Recall-Seite meldet sich von selbst, die Precision-Seite
nie (dieselbe Hausregel wie beim Guard, #62).
"""

from __future__ import annotations

import re

# Nur Plural: siehe Entwurfsregel 1 im Modul-Docstring.
_NEWS_NOUN = re.compile(
    r"\b(nachrichten\w*|schlagzeilen|neuigkeiten|news|briefing|meldungen)\b",
    re.IGNORECASE,
)

# Kurze Brücken, die keine Teilsatzgrenze überspringen — wie beim Guard (#62).
_NEWS_PHRASE = re.compile(
    r"was\s+gibt(?:'s|\s+es)\b[^,.!?\n]{0,25}\bneues"
    r"|was\s+ist\b[^,.!?\n]{0,30}\bpassiert",
    re.IGNORECASE,
)

# „bei dir", „von euch", „aus deinem Leben" — Small Talk, keine Nachrichten.
_PERSONAL = re.compile(r"\b(bei|von|über)\s+(dir|euch)\b|\baus\s+dein", re.IGNORECASE)

# Kürzer als das taugt ein Namensteil nicht als Auslöser: „Der Spiegel" darf
# nicht an jedem „der" hängen.
_MIN_FEED_WORD = 4


def feed_aliases(name: str) -> tuple[str, ...]:
    """Unter welchen Namen ist dieser Feed ansprechbar?

    Der volle Name plus jedes Wort daraus ab vier Zeichen — „heise online"
    hört damit auch auf „heise", „Der Spiegel" auf „Spiegel". Die Liste kommt
    aus der Config, nicht aus einer gepflegten Wortliste: **wer einen Feed
    ergänzt, bekommt seinen Auslöser geschenkt.**
    """
    lowered = (name or "").strip().lower()
    if not lowered:
        return ()
    words = [w for w in re.split(r"\W+", lowered) if len(w) >= _MIN_FEED_WORD]
    return tuple(dict.fromkeys([lowered, *words]))


def feeds_for_question(question: str, feed_names: list[str]) -> tuple[str, ...]:
    """Welche Feeds gehören zu dieser Frage?

    Leeres Tupel heißt: **nichts injizieren**. Sonst die Namen der Feeds, deren
    Meldungen in den Kontext gehören — ein Name, wenn die Frage eine Quelle
    ausdrücklich nennt, sonst alle.
    """
    text = (question or "").strip()
    if not text:
        return ()

    for name in feed_names or []:
        for alias in feed_aliases(name):
            if re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
                return (name,)

    # Der Personenbezug wird **vor** den Nachrichtenwörtern geprüft: „Was
    # gibt's Neues bei dir?" enthält die Phrase und ist trotzdem Small Talk.
    if _PERSONAL.search(text):
        return ()

    if _NEWS_NOUN.search(text) or _NEWS_PHRASE.search(text):
        return tuple(feed_names or [])
    return ()
