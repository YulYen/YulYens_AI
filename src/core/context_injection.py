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


def conversation_only(
    messages: Iterable[Mapping[str, Any]] | None
) -> list[dict[str, Any]]:
    """Der Gesprächsstand ohne injizierten Fremdkontext.

    Für alle Verbraucher, die das *Gespräch* meinen und nicht den Prompt:
    Ablage, JSON-Export, Markdown. Die Kopie ist Absicht — der Aufrufer soll
    nicht versehentlich in der Prompt-History herumschreiben.
    """
    return [dict(message) for message in messages or [] if not is_injected(message)]
