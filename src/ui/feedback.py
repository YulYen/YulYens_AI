"""Die 👍/👎-Bewertungen der WebUI (#40) samt Schlüssel in die Ablage (#65).

Herausgelöst aus `web_ui.py` (#56). Das ist nicht bloß Zeilenverschieben: von
allem in dieser Datei ist das hier die Logik mit den höchsten Einsätzen, weil
aus ihr später **Trainingsdaten** werden (#7). Ein falsch zugeordneter Vote
sieht genauso aus wie ein richtiger — er fällt nie auf, sondern verschiebt
still, was das Modell lernt.

Die Regeln, die man beim Umbauen leicht umdreht, stehen deshalb hier bei der
Sache statt zwischen zweitausend Zeilen Oberfläche:

1. **Gezählt werden Positionen, nicht Texte.** Zweimal „Ja." im selben
   Gespräch ist keine Seltenheit; ein Textvergleich zeigte still auf die erste
   Stelle.
2. **Eine Bot-Bubble ist nicht automatisch eine Modellantwort.** Wiki-Hinweise,
   Briefing-Meldungen und die Kompressionswarnung stehen in derselben Spalte.
   Erkannt werden sie daran, dass Beiwerk **nie in der LLM-History** landet —
   wer eine neue Hinweis-Bubble einführt, bekommt den Schutz geschenkt,
   solange er sie nicht ins Kontextfenster gibt.
3. **Im Zweifel keine Zeile.** Was sich nicht gegen die History prüfen lässt,
   wird verworfen: eine verlorene Bewertung ist billiger als eine erfundene.
4. **Die Ablage hat das letzte Wort über den Wortlaut**, nicht die Anzeige —
   gegen sie wird später gejoint.
5. **Die Datei liegt neben der Ablage, nicht im Logverzeichnis.** Sie ist
   gesammelte menschliche Bewertung: nicht reproduzierbar, nicht nachträglich
   erzeugbar, und über `conversation_id` an genau die Datei gebunden, neben der
   sie steht. `logs/` ist Betriebs-Diagnostik und darf jederzeit geleert
   werden — dieselbe Grenze, die #54 zwischen Store und Logfile gezogen hat.
   Die Votes standen bis dahin auf der falschen Seite davon.

Der Gradio-Teil (das `LikeData`-Event) bleibt bewusst in `web_ui.py`: hier
kommen nur einfache Werte an, damit das Ganze ohne Oberfläche prüfbar bleibt.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any

from core.utils import ensure_dir_exists
from ui.webui_format import ChatMessage, bubble_text, find_question_for_row

Message = dict[str, str]

# Eine Datei, mehrere Browser-Sitzungen: der Anhang wird serialisiert.
_log_lock = threading.Lock()

VOTES_FILENAME = "feedback_votes.jsonl"
# Neben der Ablage, nicht im Logverzeichnis — Begründung im Modulkopf, Punkt 5.
DEFAULT_VOTES_DIR = "data"
# Wo die Datei bis dahin lag. Nur noch für den Umzug relevant.
LEGACY_VOTES_DIR = "logs"


def adopt_legacy_votes(target: str, legacy_dir: str = LEGACY_VOTES_DIR) -> str:
    """Holt eine Vote-Datei aus dem alten Logverzeichnis herüber.

    Der Pfad hat sich geändert, und **ein Pfadwechsel ohne Umzug verliert
    stillschweigend Daten**: die alten Zeilen lägen weiter in `logs/`, neue
    kämen in `data/` dazu, und niemandem fiele es auf, bis jemand die
    Trainingsdaten für #7 zusammenstellt und die Hälfte fehlt.

    Verschoben wird nur im **eindeutigen** Fall — alt da, neu nicht. Liegen
    beide, wird nichts angefasst und laut gewarnt: welche der beiden Dateien
    dann die richtige ist, kann hier niemand entscheiden, und ein automatisches
    Zusammenführen wäre geraten statt gewusst.
    """
    legacy = os.path.join(legacy_dir, VOTES_FILENAME)
    if not os.path.exists(legacy):
        return target

    if os.path.exists(target):
        logging.warning(
            "[FEEDBACK] %s und %s existieren beide. Es wird nur %s beschrieben — "
            "die alte Datei bitte von Hand anhängen und entfernen.",
            legacy,
            target,
            target,
        )
        return target

    try:
        os.replace(legacy, target)
        logging.info("[FEEDBACK] Vote-Log von %s nach %s verschoben.", legacy, target)
    except OSError as err:
        # Lieber am alten Ort weiterschreiben als gar nicht: eine verlorene
        # Bewertung ist teurer als ein unaufgeräumtes Verzeichnis.
        logging.warning(
            "[FEEDBACK] Umzug von %s nach %s fehlgeschlagen (%s) — "
            "es wird weiter am alten Ort geschrieben.",
            legacy,
            target,
            err,
        )
        return legacy
    return target


def store_index_of(
    text: str,
    row: int,
    chat_history: list[ChatMessage] | None,
    llm_history: list[Message] | None,
) -> int | None:
    """Welche Nachricht der **Ablage** ist die angeklickte Bubble? (#65)

    Der Anzeige-Index taugt dafür nicht: in ``chat_history`` stehen
    Hinweis-Bubbles zwischen den Antworten, in der Ablage nicht. Ein Vote mit
    `index: 2` (vor #61a: `[2, 1]`) war deshalb eine UI-Koordinate und ließ
    sich mit nichts verbinden.

    Gezählt wird stattdessen **die Position unter den Modellantworten**: die
    k-te Antwort-Bubble ist die k-te ``assistant``-Nachricht, weil Anzeige und
    LLM-Verlauf im Gleichschritt wachsen (auch „Nochmal 🔄" entfernt aus
    beiden). ``ConversationStore.sync`` nummeriert genau diese Folge durch —
    Systemkontext filtert es heraus —, also stimmt der Index auf beiden Seiten.
    """
    answers = {
        (m.get("content") or "").strip()
        for m in (llm_history or [])
        if m.get("role") == "assistant"
    }
    candidate = (text or "").strip()
    if not candidate or candidate not in answers:
        return None

    # Wievielte Antwort-Bubble ist die angeklickte? Seit #61a ist eine
    # Anzeige-Zeile *eine* Nachricht, der Zähler liest also `role`; die
    # Zählregel selbst ist unverändert.
    seen = 0
    for idx, message in enumerate(chat_history or []):
        if message.get("role") == "assistant":
            bubble = bubble_text(message).strip()
            if bubble and bubble in answers:
                seen += 1
        if idx == row:
            break
    if seen == 0:
        return None

    # … und die wievielte Nachricht ist das in der Ablage?
    position = 0
    for store_idx, message in enumerate(
        [m for m in (llm_history or []) if m.get("role") in ("user", "assistant")]
    ):
        if message.get("role") != "assistant":
            continue
        position += 1
        if position == seen:
            return store_idx
    return None


class FeedbackLog:
    """Schreibt die Votes — append-only, eine Zeile je Bewertung.

    ``store_loader`` liefert den aufgezeichneten Wortlaut einer Nachricht und
    darf still fehlschlagen: ohne Anmeldung gibt es keine Ablage (#72), und
    ein Vote ohne Store-Text ist besser als kein Vote.
    """

    def __init__(
        self,
        path: str | None = None,
        *,
        data_dir: str = DEFAULT_VOTES_DIR,
        store_loader: Callable[[str, int], str | None] | None = None,
        fallback_user: Callable[[], str] = lambda: "local",
    ) -> None:
        self._path = path
        self._data_dir = data_dir
        self._store_loader = store_loader
        self._fallback_user = fallback_user

    @property
    def path(self) -> str:
        if not self._path:
            ensure_dir_exists(self._data_dir)
            target = os.path.join(self._data_dir, VOTES_FILENAME)
            self._path = adopt_legacy_votes(target)
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = value

    def record(
        self,
        *,
        row: Any,
        liked: bool,
        value: Any,
        chat_history: list[ChatMessage] | None,
        llm_history: list[Message] | None,
        meta: dict | None,
        conversation_id: str | None,
        persona: str = "",
    ) -> bool:
        """Eine Bewertung aufzeichnen. ``True``, wenn eine Zeile entstand.

        Ein Vote darf **nie** die Oberfläche zerreißen: jeder Fehlschlag wird
        protokolliert und geschluckt.
        """
        try:
            # Ein nicht deutbarer Index wird verworfen statt geraten. Der
            # frühere Rückfall (`row = -1`) ließ den Zähler *alle* Bubbles
            # sehen und schrieb den Vote auf die letzte Antwort — eine
            # plausibel aussehende, falsch zugeordnete Trainingszeile.
            try:
                index = int(row)
            except (TypeError, ValueError):
                logging.warning("Feedback vote with unexpected index %r", row)
                return False

            history = chat_history or []
            message = history[index] if 0 <= index < len(history) else None
            if not isinstance(message, dict):
                logging.warning("Feedback vote on index %s outside the history", index)
                return False

            # Eine Bewertung der eigenen Frage ist kein Trainingssignal.
            if message.get("role") != "assistant":
                logging.debug("Ignoring feedback vote on a user message (%s)", index)
                return False

            answer = bubble_text(message) or str(value)

            message_index = store_index_of(answer, index, history, llm_history)
            if message_index is None:
                logging.debug(
                    "Ignoring feedback vote on a UI notice, not a model answer (%s)",
                    index,
                )
                return False

            conversation_id = str(conversation_id or "")
            answer = self._from_store(conversation_id, message_index) or answer

            meta = meta if isinstance(meta, dict) else {}
            entry = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "app": meta.get("app", "web"),
                "user": meta.get("user") or self._fallback_user(),
                "persona": meta.get("persona") or persona or "",
                "model": meta.get("model", ""),
                "vote": "up" if liked else "down",
                "question": find_question_for_row(history, index),
                "answer": answer,
                # Der Join-Schlüssel (#65). `conversation_id` ist leer, wenn
                # ohne Anmeldung nichts aufgezeichnet wird (#72) — dann bleibt
                # der Vote das, was er vorher immer war.
                "conversation_id": conversation_id,
                "message_index": message_index,
                # Die UI-Koordinate bleibt zur Diagnose daneben stehen.
                "index": index,
            }
            with _log_lock:
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return True
        except (OSError, TypeError, ValueError, AttributeError):
            logging.exception("Could not write feedback log %s", self._path)
            return False

    def _from_store(self, conversation_id: str, index: int) -> str | None:
        if not conversation_id or self._store_loader is None:
            return None
        try:
            return self._store_loader(conversation_id, index)
        except (AttributeError, IndexError, TypeError, KeyError):
            logging.debug("Vote: kein Text aus der Ablage für %s", conversation_id)
            return None
