"""Was zu *einer* Browser-Sitzung der WebUI gehört.

Die `WebUI` ist ein Singleton der `AppFactory` — sie wird einmal gebaut und
bedient alle Browser. Persona, Streamer und die Kill-Switches am Objekt zu
halten hieß deshalb: **zwei gleichzeitige Sitzungen teilen sie sich.** Wählt A
LEAH und B danach DORIS, landet A's nächste Frage bei DORIS, samt Eintrag in
deren Gespräch.

Der Zustand gehört also in ein `gr.State` — genau dorthin, wo `history_state`,
`user_state` und `conversation_state` längst liegen. Gradio legt für jede
Browser-Sitzung **eine eigene Kopie** des Default-Werts an
(`SessionState.__getitem__` in `gradio/state_holder.py` macht einmalig ein
`deepcopy` und merkt sie sich), deshalb genügt es, dieses Objekt als `inputs=`
durchzureichen und in-place zu ändern — es muss nicht als Output zurück.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionContext:
    """Der Zustand einer Browser-Sitzung. Default-Instanz = frische Sitzung."""

    # Gewählte Persona und ihr Streamer. Beide sind None, solange die Sitzung
    # auf dem Startraster steht.
    bot: str | None = None
    streamer: Any = None

    # Kill switch für Einzelchat/Briefing/Self-Talk (#35) bzw. für den
    # Ask-All-Broadcast. Nötig, weil Gradios `cancels` nur den asyncio-Task
    # abbricht: das `finally` eines laufenden Generator-Handlers läuft dabei
    # nicht zuverlässig, die Arbeit im Backend liefe weiter.
    stream_stop: threading.Event | None = None
    ask_all_stop: threading.Event | None = None

    # Läuft ein AI-Dialog, gehört auch dessen Runner der Sitzung.
    self_talk_runner: Any = None

    # Temporäre Dateien, die diese Sitzung ausliefert (WAV, JSON, Markdown) —
    # je Art die zuletzt erzeugte. Sie muss den Response überleben, die
    # vorherige darf beim nächsten Mal weg.
    tmp_files: dict[str, str] = field(default_factory=dict)

    def clear_persona(self) -> None:
        """Zurück aufs Startraster: keine Persona, kein Streamer."""
        self.bot = None
        self.streamer = None
