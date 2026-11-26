"""Injizierter Fremdkontext: markierte Nachrichten in der ``user``-Rolle (#60).

Wiki-Snippets und RSS-Meldungen standen bis hierher als ``system``-Nachricht im
Prompt — also mit **höchster** Autorität, direkt neben der Anweisung, ihr
ausschließlich zu folgen. Für Text aus einer heruntergeladenen ZIM-Datei oder
einem abonnierten Feed ist das die falsche Ebene: er ist Material, über das
geredet wird, keine Anweisung.

Die Rolle allein umzustellen genügt nicht. ``system`` war nebenbei das Merkmal,
an dem die Ablage (``storage.store.sync``) den Fremdtext vom Gespräch getrennt
hat — sie filtert auf ``user``/``assistant``. Ohne Ersatz landet jeder
Wikipedia-Artikel ab sofort in der SQLite-Ablage, im Verlauf, im
Markdown-Export und im JSON-Download. Der Marker hier *ist* dieser Ersatz und
muss deshalb an **jeder** injizierten Nachricht hängen.

Warum ein Zusatzfeld am Dict und keine Erkennung am Text: eine Prüfung auf die
Zitat-Klammer wäre Textschnüffelei an Inhalt, den der Nutzer selbst tippen
kann. Ollama reicht unbekannte Felder folgenlos durch (am echten Modell
geprüft), die Ablage und der JSON-Export lassen sie fallen.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Absichtlich sprechend und projekt-eigen: ein generisches "injected" könnte
# irgendwann mit einem Feld einer LLM-API kollidieren.
INJECTED_KEY = "yulyen_injected"


def injected_message(content: str, source: str) -> dict[str, Any]:
    """Eine Kontext-Nachricht: ``user``-Rolle, als Fremdtext markiert.

    ``source`` ist die Herkunft (``"wiki"``, ``"rss"``) — sie kostet nichts und
    macht einen Mitschnitt lesbar, wenn jemand später fragt, woher ein Block kam.
    """
    return {"role": "user", "content": content, INJECTED_KEY: source}


def is_injected(message: Mapping[str, Any]) -> bool:
    return bool(message.get(INJECTED_KEY))


# Der Gegenfall zum injizierten Fremdtext: eine Nachricht, die **zum Gespräch
# gehört, aber nicht mehr in den Prompt geht**, weil die Kontext-Kompression
# (Karl, heuristischer Trim) sie herausgenommen hat.
#
# Vorher wurden solche Nachrichten aus dem Verlauf *gelöscht*. Der Verlauf ist
# aber zugleich das, was die Oberfläche in die Ablage spiegelt — mit der ersten
# Kompression verlor das gespeicherte Gespräch deshalb seinen Anfang, samt
# Titel. Markieren statt löschen hält beides in **einer** Liste: wer das
# Gespräch meint (Ablage, Export, Votes), sieht alles; wer den Prompt meint
# (``stream()``, Füllstand), fragt ``prompt_only``.
COMPRESSED_KEY = "yulyen_compressed"


def is_compressed(message: Mapping[str, Any]) -> bool:
    return bool(message.get(COMPRESSED_KEY))


def compressed_copy(message: Mapping[str, Any]) -> dict[str, Any]:
    """Dieselbe Nachricht, als „nicht mehr im Prompt" markiert."""
    return {**message, COMPRESSED_KEY: True}


def prompt_only(
    messages: Iterable[Mapping[str, Any]] | None,
) -> list[Any]:
    """Was tatsächlich an das Modell geht — ohne die komprimierten Turns.

    Dieselben Objekte, keine Kopien: der Aufrufer reicht sie an das Backend
    weiter oder zählt sie, er schreibt nicht hinein.
    """
    return [message for message in messages or [] if not is_compressed(message)]


def conversation_only(
    messages: Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Der Gesprächsstand ohne injizierten Fremdkontext.

    Für alle Verbraucher, die das *Gespräch* meinen und nicht den Prompt:
    Ablage, JSON-Export, Markdown. Die Kopie ist Absicht — der Aufrufer soll
    nicht versehentlich in der Prompt-History herumschreiben. Komprimierte
    Turns bleiben drin (sie *sind* Gespräch), nur ihre Markierung nicht: die
    beschreibt den Prompt-Zustand einer Sitzung und hat in einer Datei nichts
    verloren.
    """
    return [
        {key: value for key, value in message.items() if key != COMPRESSED_KEY}
        for message in messages or []
        if not is_injected(message)
    ]


def recorded_turns(
    messages: Iterable[Mapping[str, Any]] | None,
) -> list[Mapping[str, Any]]:
    """Die Nachrichten, die in der Ablage stehen — in deren Reihenfolge.

    Nur ``user`` und ``assistant``, und davon nichts Injiziertes. **Eine**
    Stelle für diese Regel, weil zwei Seiten sie brauchen und sich nicht
    widersprechen dürfen: ``SqliteStore.sync`` nummeriert genau diese Folge
    durch, und der Vote-Kanal (``ui/feedback.py``) zählt in ihr, um auf eine
    Nachricht der Ablage zu zeigen. Als #60 den Fremdtext von ``system`` nach
    ``user`` verlegte, zog nur die Ablage nach — die Zählregel zählte ihn
    weiter mit, und jeder Vote nach einem Wiki-Treffer zeigte eine Nachricht
    zu weit.
    """
    return [
        message
        for message in messages or []
        if message.get("role") in ("user", "assistant") and not is_injected(message)
    ]
