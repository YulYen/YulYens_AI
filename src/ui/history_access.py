"""Zugriff auf gespeicherte Gespräche für die Verlauf-Karte (#25/#56).

Herausgelöst aus `web_ui.py`, weil hier eine **Sicherheitszusage** wohnt und
nicht bloß Datenbeschaffung: jeder Weg in ein fremdes Gespräch führt durch
diese drei Methoden, und alle drei reichen den Nutzer an die Ablage durch.

Der Grund steht in Review-Runde 2: die Gesprächs-ID kommt aus einem
``gr.Dropdown``, und dessen ``preprocess`` reichte den Wert des Clients
ungeprüft durch (GHSA-26jh-r8g2-6fpr). Die Auswahl im Browser ist also **keine
Schranke** — wer eine fremde ID kannte, konnte das Gespräch lesen,
exportieren, fortsetzen und löschen. Nachgestellt mit zwei angemeldeten
Nutzern.

Die Prüfung liegt deshalb an der Stelle, an der alle Handler zwangsläufig
vorbeikommen, statt viermal beim Aufrufer. Wer einen **fünften** Weg in ein
gespeichertes Gespräch baut, nimmt ihn hier — nicht am Store vorbei.

Ein fremdes Gespräch verhält sich wie ein nicht existierendes: die Antwort
soll nicht verraten, dass es die ID gibt.
"""

from __future__ import annotations

import logging
from typing import Any

from ui.webui_format import history_label

DEFAULT_HISTORY_LIMIT = 50


class ConversationHistory:
    """Liest und löscht Gespräche — immer nutzergebunden.

    ``store_getter`` statt eines Stores: die Ablage kommt aus der Factory und
    kann zur Laufzeit ein ``NullStore`` sein (#72). Ein Fehlschlag darf die
    Oberfläche nie zerreißen, deshalb wird geloggt und leer zurückgegeben.
    """

    def __init__(
        self,
        store_getter,
        *,
        limit: Any = DEFAULT_HISTORY_LIMIT,
        fallback_user: str = "local",
    ) -> None:
        self._store_getter = store_getter
        self._fallback_user = fallback_user
        try:
            self.limit = max(1, int(limit))
        except (TypeError, ValueError):
            self.limit = DEFAULT_HISTORY_LIMIT

    def _user(self, user: str | None) -> str:
        return user or self._fallback_user

    def choices(self, user: str | None) -> list[tuple[str, str]]:
        """Beschriftung und ID der Gespräche **dieses** Nutzers.

        Die Filterung ist der Grund, warum #53 (Identität) vor #25 kam: ohne
        sie zeigt eine Verlaufsliste jedem alles.
        """
        try:
            refs = self._store_getter().list_conversations(
                user=self._user(user), limit=self.limit
            )
        except Exception:
            logging.exception("Verlauf konnte nicht gelesen werden")
            return []
        return [(history_label(ref), ref.id) for ref in refs]

    def load(self, conversation_id: str | None, user: str | None):
        """Ein Gespräch — oder ``None``, auch wenn es einem anderen gehört."""
        if not conversation_id:
            return None
        try:
            return self._store_getter().load(
                str(conversation_id), user=self._user(user)
            )
        except Exception:
            logging.exception("Gespräch %s nicht ladbar", conversation_id)
            return None

    def delete(self, conversation_id: str | None, user: str | None) -> bool:
        if not conversation_id:
            return False
        try:
            return bool(
                self._store_getter().delete(str(conversation_id), user=self._user(user))
            )
        except Exception:
            logging.exception("Gespräch %s nicht löschbar", conversation_id)
            return False
