"""Ablage der Gespräche (#54).

**Warum es das gibt:** bis hierher war das Gesprächs-*Logfile* die Persistenz.
Das hatte drei konkrete Folgen: es gab zwei unvereinbare Formate (JSONL im
Archiv, `{"meta":…, "messages":…}` beim Download), ein Gespräch war kein
eigenständiges Ding sondern hing an der Lebensdauer eines Streamer-Objekts (es
gab keine ID, an der man es hätte festmachen können), und Suchen oder Filtern
hätte bedeutet, alle Dateien zu lesen.

**Warum SQLite:** es ist stdlib (keine neue Abhängigkeit), eine Datei, atomar,
Windows-tauglich. Und #49 (Volltextsuche) bekommt mit FTS5 einen Index
geschenkt, statt dass man sich einen bauen muss. Der Preis ist ehrlich: die
Datei lässt sich nicht mehr mit ``grep`` lesen — dafür bleibt der JSONL-Mitschnitt
als ausdrückliches Debug-Artefakt erhalten (`logging.conversation_jsonl`).

**Migrationen** laufen über ``PRAGMA user_version`` plus eine geordnete Liste
von SQL-Schritten. Kein Framework, aber erweiterbar: die FTS5-Tabelle für #49
wird schlicht Schritt Nr. 2. Einen Index vor dem Sucher anzulegen wäre
Vorratshaltung, deshalb ist er noch nicht da.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from core.utils import LOCAL_USER, ensure_dir_exists

# Wie viel der ersten Frage als Titel in der Liste steht.
_TITLE_MAX_CHARS = 80

# Jeder Schritt hebt user_version um eins. Nie einen Schritt ändern, der schon
# ausgeliefert wurde — nur anhängen.
_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE conversations (
        id           TEXT PRIMARY KEY,
        user         TEXT NOT NULL,
        persona      TEXT NOT NULL,
        model        TEXT NOT NULL,
        app          TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        updated_at   TEXT NOT NULL,
        title        TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE messages (
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        idx             INTEGER NOT NULL,
        role            TEXT NOT NULL,
        content         TEXT NOT NULL,
        ts              TEXT NOT NULL,
        PRIMARY KEY (conversation_id, idx)
    );
    CREATE INDEX idx_conversations_user_updated
        ON conversations(user, updated_at DESC);
    """,
)


@dataclass(frozen=True)
class ConversationRef:
    """Kopfdaten eines Gesprächs — für Listen, ohne die Nachrichten zu laden."""

    id: str
    user: str
    persona: str
    model: str
    app: str
    created_at: str
    updated_at: str
    title: str
    message_count: int


class ConversationStore(Protocol):
    def start(self, *, user: str, persona: str, model: str, app: str) -> str: ...

    def append(self, conversation_id: str, role: str, content: str) -> None: ...

    def list_conversations(
        self, *, user: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ConversationRef]: ...

    def load(
        self, conversation_id: str
    ) -> tuple[ConversationRef, list[dict[str, str]]] | None: ...

    def delete(self, conversation_id: str) -> bool: ...


class NullStore:
    """Schreibt nichts. Für Tests und für alle, die keine Ablage wollen."""

    def start(self, *, user: str, persona: str, model: str, app: str) -> str:
        return ""

    def append(self, conversation_id: str, role: str, content: str) -> None:
        return None

    def list_conversations(
        self, *, user: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ConversationRef]:
        return []

    def load(
        self, conversation_id: str
    ) -> tuple[ConversationRef, list[dict[str, str]]] | None:
        return None

    def delete(self, conversation_id: str) -> bool:
        return False


class SqliteStore:
    """Gespräche in einer SQLite-Datei.

    Eine Verbindung plus Lock statt Verbindung-pro-Thread: die Gradio-Handler
    laufen nebenläufig, aber die Schreiblast ist eine Zeile pro Turn — dasselbe
    Muster, das der bisherige Log mit ``_conversation_log_lock`` benutzt hat.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        ensure_dir_exists(self.path.parent)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        # WAL: Lesen (Verlauf-Liste) blockiert Schreiben (laufender Stream) nicht.
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def _migrate(self) -> None:
        with self._lock:
            version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            for step, sql in enumerate(_MIGRATIONS[version:], start=version + 1):
                self._conn.executescript(sql)
                self._conn.execute(f"PRAGMA user_version = {step}")
                self._conn.commit()
                logging.info("[STORE] Schema auf Version %s gebracht", step)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def start(self, *, user: str, persona: str, model: str, app: str) -> str:
        conversation_id = uuid.uuid4().hex
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations "
                "(id, user, persona, model, app, created_at, updated_at, title) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, '')",
                (
                    conversation_id,
                    (user or "").strip() or LOCAL_USER,
                    persona,
                    model,
                    app,
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return conversation_id

    def append(self, conversation_id: str, role: str, content: str) -> None:
        if not conversation_id:
            return
        now = _now()
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(idx), -1) + 1 AS next FROM messages "
                "WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            idx = int(row["next"])
            self._conn.execute(
                "INSERT INTO messages (conversation_id, idx, role, content, ts) "
                "VALUES (?, ?, ?, ?, ?)",
                (conversation_id, idx, role, content, now),
            )
            # Der Titel ist die erste Nutzerfrage — er entsteht beiläufig, statt
            # später aus dem Verlauf zurückgerechnet werden zu müssen.
            if idx == 0 and role == "user":
                self._conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (_make_title(content), now, conversation_id),
                )
            else:
                self._conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now, conversation_id),
                )
            self._conn.commit()

    def list_conversations(
        self, *, user: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ConversationRef]:
        query = (
            "SELECT c.*, (SELECT COUNT(*) FROM messages m "
            "             WHERE m.conversation_id = c.id) AS message_count "
            "FROM conversations c "
        )
        params: list[Any] = []
        if user:
            query += "WHERE c.user = ? "
            params.append(user)
        query += "ORDER BY c.updated_at DESC LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [_to_ref(row) for row in rows]

    def load(
        self, conversation_id: str
    ) -> tuple[ConversationRef, list[dict[str, str]]] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM messages m "
                "             WHERE m.conversation_id = c.id) AS message_count "
                "FROM conversations c WHERE c.id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return None
            messages = self._conn.execute(
                "SELECT role, content FROM messages "
                "WHERE conversation_id = ? ORDER BY idx",
                (conversation_id,),
            ).fetchall()
        return _to_ref(row), [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM conversations WHERE id = ?", (conversation_id,)
            )
            self._conn.commit()
            return cursor.rowcount > 0


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _make_title(content: str) -> str:
    text = " ".join((content or "").split())
    if len(text) <= _TITLE_MAX_CHARS:
        return text
    return text[:_TITLE_MAX_CHARS].rstrip() + " …"


def _to_ref(row: sqlite3.Row) -> ConversationRef:
    return ConversationRef(
        id=row["id"],
        user=row["user"],
        persona=row["persona"],
        model=row["model"],
        app=row["app"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        title=row["title"],
        message_count=int(row["message_count"]),
    )


def build_store(storage_cfg: dict | None) -> ConversationStore:
    """Baut den Store aus der ``storage``-Sektion; ausgeschaltet = NullStore."""
    cfg = storage_cfg or {}
    if not cfg.get("enabled", True):
        logging.info("[STORE] Gesprächs-Ablage ist ausgeschaltet (storage.enabled)")
        return NullStore()
    path = str(cfg.get("path") or "data/conversations.sqlite3")
    try:
        return SqliteStore(path)
    except sqlite3.Error as exc:
        # Eine kaputte Datei darf die App nicht am Start hindern — dann eben
        # ohne Ablage, aber laut.
        logging.error(
            "[STORE] Ablage '%s' nicht nutzbar (%s) — es wird nichts gespeichert.",
            path,
            exc,
        )
        return NullStore()
