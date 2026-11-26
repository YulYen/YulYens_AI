"""Darf dieses gespeicherte Gespräch als Ensemble-Persona fortgesetzt werden?

**Warum als eigenes Modul.** Es gibt *drei* Wege, ein gespeichertes Gespräch
wieder aufzunehmen, und alle drei lesen dasselbe Format:

1. Verlauf → Öffnen (WebUI, aus der Ablage)
2. „Konversation hochladen" (WebUI, JSON-Datei)
3. Startmenü → Laden bzw. der Ladepfad im Terminal (`conversation_io_terminal`)

#55 hat die Regel zweimal gebaut und damit Weg 2 offen gelassen; die Korrektur
zog die Prüfung auf Primitiven zusammen, blieb aber in `web_ui.py` liegen — und
übersah damit Weg 3. Das Terminal prüfte lediglich, ob der Personenname im
Ensemble vorkommt, und setzte ein Gast-Gespräch stillschweigend als die echte
Persona fort.

Die Regel gehört deshalb dorthin, wo alle drei sie sehen, statt an eine der
Oberflächen. Bewusst auf Primitiven (`str`, `dict`) statt auf
`ConversationRef`: Weg 2 und 3 haben nur die Metadaten aus einer JSON-Datei,
kein Store-Objekt.
"""

from __future__ import annotations

from typing import Any

# Marker im `app`-Feld eines Gesprächs, das eine Gast-Persona geführt hat.
# Gast-Personas leben nur in ihrer Sitzung (#28) — ihr System-Prompt existiert
# danach nirgends mehr.
GUEST_APP = "web-guest"


def continuable_persona(
    persona_name: str | None,
    app: str | None,
    persona_info: dict[str, dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Die Ensemble-Persona zu einem Gespräch — oder ``None``.

    Zwei Hürden, weil eine allein nicht reicht: Gast-Gespräche tragen ein
    eigenes ``app``, und der Name muss **exakt** stimmen. Sonst öffnete ein Gast
    namens „Leah" das Gespräch still als die echte LEAH weiter, weil die
    Auflösung über ``persona.lower()`` läuft — ohne jeden Hinweis, dass ab da
    ein anderer System-Prompt antwortet. Die Namensprüfung deckt zusätzlich
    Gast-Gespräche ab, die vor der Einführung des eigenen ``app`` entstanden
    sind.
    """
    if app == GUEST_APP:
        return None
    persona = (persona_info or {}).get((persona_name or "").lower())
    if not persona or persona.get("name") != persona_name:
        return None
    return persona


def persona_info_from_names(names: list[str]) -> dict[str, dict[str, Any]]:
    """Baut die Nachschlagetabelle für Oberflächen, die nur Namen haben.

    Die WebUI hält ohnehin ein ``persona_info`` mit Beschreibungen und Bildern;
    das Terminal kennt nur ``get_all_persona_names()``. Damit beide dieselbe
    Prüfung aufrufen können, kommt hier die minimale Form heraus — inklusive
    des exakten Namens, an dem der Gast-Fall hängt.
    """
    return {name.lower(): {"name": name} for name in names}
