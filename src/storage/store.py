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

import atexit
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from core.context_injection import is_injected
from core.utils import LOCAL_USER, ensure_dir_exists

# Wohin die Ablage schreibt, wenn `storage.path` nichts sagt. Als Konstante,
# damit die Testsuite sie umbiegen kann: ein Config-Objekt ohne `storage`-Feld
# landete sonst hier und legte die Datei im Repo an (#64f).
DEFAULT_STORE_PATH = "data/conversations.sqlite3"

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
    # Schritt 2 — Volltextsuche (#49). External-Content-Index über die implizite
    # `rowid` von `messages`: FTS5 hält nur den Index, der Text bleibt einmal in
    # `messages`. Der Backfill gehört in denselben Schritt — ohne ihn wären alle
    # *bestehenden* Gespräche unsichtbar, und das fiele erst dem auf, der lange
    # sucht und nichts findet.
    """
    CREATE VIRTUAL TABLE messages_fts USING fts5(content, content='messages');
    INSERT INTO messages_fts(rowid, content) SELECT rowid, content FROM messages;
    CREATE TRIGGER messages_fts_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
    END;
    CREATE TRIGGER messages_fts_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
    END;
    CREATE TRIGGER messages_fts_au AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
            VALUES ('delete', old.rowid, old.content);
        INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
    END;
    """,
)

# Schritte, die auf einer Zielmaschine fehlschlagen *dürfen*, ohne dass die
# Ablage als kaputt gilt.
#
# Nötig geworden mit Schritt 2: ein SQLite ohne FTS5-Modul ist kein Defekt der
# Datei. Ohne diese Liste risse der Schritt aber die **ganze** Ablage mit —
# `_migrate` wirft, `build_store` fängt jede `sqlite3.Error` mit einem
# `NullStore` ab, und die App liefe weiter, ohne noch irgendetwas aufzuzeichnen.
# Genau die stille Sorte Verhaltensänderung, die #72 so teuer gemacht hat: der
# Nutzer verlöre seinen Verlauf und bekäme dafür eine Logzeile.
#
# Ein fehlgeschlagener optionaler Schritt **hält die Kette an** (kein `continue`):
# Schritt 3 auf einer Datei anzuwenden, die Schritt 2 nie gesehen hat, wäre ein
# Schema, das es in keiner Version je gab.
_OPTIONAL_MIGRATIONS: frozenset[int] = frozenset({2})


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


@dataclass(frozen=True)
class SearchHit:
    """Eine Fundstelle der Volltextsuche (#49).

    Trägt den Gesprächskopf mit, damit eine Trefferliste ohne zweiten Zugriff
    „Persona, Datum, Fundstelle" zeigen kann — dasselbe Motiv wie bei
    ``ConversationRef``.
    """

    conversation_id: str
    persona: str
    updated_at: str
    title: str
    role: str
    idx: int
    snippet: str


class ConversationStore(Protocol):
    #: Ob diese Ablage wirklich schreibt. Die Oberfläche fragt danach, statt zu
    #: raten: eine Verlauf-Karte über einem ``NullStore`` verspricht etwas, das
    #: sich nie füllen kann.
    records: bool

    def start(self, *, user: str, persona: str, model: str, app: str) -> str: ...

    def append(self, conversation_id: str, role: str, content: str) -> None: ...

    def sync(self, conversation_id: str, messages: list[dict[str, str]]) -> None: ...

    def list_conversations(
        self, *, user: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ConversationRef]: ...

    def load(
        self, conversation_id: str, *, user: str | None = None
    ) -> tuple[ConversationRef, list[dict[str, str]]] | None: ...

    def delete(self, conversation_id: str, *, user: str | None = None) -> bool: ...

    def search(
        self, query: str, *, user: str | None = None, limit: int = 50
    ) -> list[SearchHit]: ...


class NullStore:
    """Schreibt nichts. Für Tests und für alle, die keine Ablage wollen."""

    records = False

    def start(self, *, user: str, persona: str, model: str, app: str) -> str:
        return ""

    def append(self, conversation_id: str, role: str, content: str) -> None:
        return None

    def sync(self, conversation_id: str, messages: list[dict[str, str]]) -> None:
        return None

    def list_conversations(
        self, *, user: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[ConversationRef]:
        return []

    def load(
        self, conversation_id: str, *, user: str | None = None
    ) -> tuple[ConversationRef, list[dict[str, str]]] | None:
        return None

    def delete(self, conversation_id: str, *, user: str | None = None) -> bool:
        return False

    def search(
        self, query: str, *, user: str | None = None, limit: int = 50
    ) -> list[SearchHit]:
        return []


class SqliteStore:
    """Gespräche in einer SQLite-Datei.

    Eine Verbindung plus Lock statt Verbindung-pro-Thread: die Gradio-Handler
    laufen nebenläufig, aber die Schreiblast ist eine Zeile pro Turn — dasselbe
    Muster, das der bisherige Log mit ``_conversation_log_lock`` benutzt hat.
    """

    records = True

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
        # Einmal beantwortet statt bei jeder Suche: der Index fehlt genau dann,
        # wenn Schritt 2 übersprungen wurde (SQLite ohne FTS5).
        self._searchable = bool(
            self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("messages_fts",),
            ).fetchone()
        )

    def _migrate(self) -> None:
        """Wendet die ausstehenden Schritte an — jeden ganz oder gar nicht.

        Vorher lief jeder Schritt über ``executescript``. Das committet die
        laufende Transaktion *vorher* und klammert das Skript selbst nicht:
        scheiterte Anweisung 2 von 3, blieb Anweisung 1 stehen, während
        ``user_version`` auf dem alten Wert blieb. Der Schritt war damit **nie
        wieder** anwendbar — beim nächsten Start scheiterte er an „table …
        already exists", ``build_store`` degradierte zum ``NullStore``, und die
        App lief weiter, ohne noch irgendetwas aufzuzeichnen.

        Deshalb explizit ``BEGIN``/``COMMIT``: Pythons Legacy-Modus
        (``isolation_level=""``) eröffnet für DDL von sich aus keine
        Transaktion. ``user_version`` wird im selben Zug gesetzt, damit Schema
        und Versionsstand nicht auseinanderlaufen können. Das ist die
        Vorbedingung dafür, dass Schritt 2 (FTS5 für #49) gefahrlos ausgeliefert
        werden kann: fehlt FTS5 auf der Zielmaschine, bleibt die Datei einfach
        auf der alten Version stehen.
        """
        with self._lock:
            version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            for step, sql in enumerate(_MIGRATIONS[version:], start=version + 1):
                # Bewusst weiter executescript mit BEGIN/COMMIT *im* Skript,
                # statt den Text an ';' zu zerlegen: ein FTS5-Trigger bringt
                # eigene Semikolons im BEGIN…END-Rumpf mit, und ein selbstgebauter
                # Splitter wäre die nächste Falle. PRAGMA user_version ist in
                # SQLite transaktional und gehört deshalb mit hinein.
                script = f"BEGIN;\n{sql}\nPRAGMA user_version = {int(step)};\nCOMMIT;"
                try:
                    self._conn.executescript(script)
                except Exception as exc:
                    self._conn.rollback()
                    if step in _OPTIONAL_MIGRATIONS:
                        # Kein Defekt der Datei, sondern eine fehlende Fähigkeit
                        # des SQLite auf dieser Maschine (FTS5). Weiterzuwerfen
                        # hieße `NullStore`, also gar keine Ablage mehr.
                        logging.warning(
                            "[STORE] Optionaler Migrationsschritt %s übersprungen "
                            "(%s) — die Datei bleibt auf Version %s, die Ablage "
                            "arbeitet normal weiter.",
                            step,
                            exc,
                            step - 1,
                        )
                        break
                    logging.error(
                        "[STORE] Migrationsschritt %s fehlgeschlagen — die Datei "
                        "bleibt unverändert auf Version %s.",
                        step,
                        step - 1,
                    )
                    raise
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

    def sync(self, conversation_id: str, messages: list[dict[str, str]]) -> None:
        """Bringt die Ablage auf den Stand des Gesprächs — als Ganzes.

        **Warum ersetzen statt anhängen.** Die Oberfläche besitzt den
        akzeptierten Gesprächszustand; die Ablage soll ihn spiegeln. Beim
        Anhängen musste jeder Aufrufer selbst buchführen, und drei Wege taten es
        falsch: „Nochmal 🔄" hängte Frage und verworfene Antwort ein weiteres
        Mal an, „Stop ⏹" ließ die Antwort ganz weg, und Ask-All wie Self-Talk
        zeichneten gar nichts auf. Mit einem Abgleich des ganzen Verlaufs kann
        das nicht mehr auseinanderlaufen.

        Nur ``user`` und ``assistant`` landen hier, und davon nur das, was
        nicht injizierter Fremdkontext ist: Wiki-Snippets und RSS-Meldungen
        gehören zum Prompt, nicht zum Gespräch — im Verlauf wären sie Lärm.

        **Die Rollenprüfung allein reicht seit #60 nicht mehr.** Der Fremdtext
        steht jetzt als ``user`` im Prompt (er soll keine Systemautorität
        haben), sähe hier also aus wie eine Frage des Nutzers. Ohne
        ``is_injected`` landete ab diesem Umbau jeder abgerufene Artikel in der
        Ablage — und über Verlauf, Markdown-Export und JSON-Download wieder
        heraus.

        Der Preis ist ein Rewrite der Nachrichtenzeilen pro Turn. Bei einem
        Gespräch von 50 Turns sind das 100 kurze Zeilen in einer lokalen
        SQLite-Datei; die verlorene Buchführung ist den Tausch wert.
        """
        if not conversation_id:
            return
        rows = [
            (str(m.get("role")), str(m.get("content") or ""))
            for m in messages or []
            if m.get("role") in ("user", "assistant") and not is_injected(m)
        ]
        now = _now()
        first_question = next((text for role, text in rows if role == "user"), "")
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.execute(
                    "DELETE FROM messages WHERE conversation_id = ?",
                    (conversation_id,),
                )
                self._conn.executemany(
                    "INSERT INTO messages (conversation_id, idx, role, content, ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        (conversation_id, idx, role, text, now)
                        for idx, (role, text) in enumerate(rows)
                    ],
                )
                self._conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (_make_title(first_question), now, conversation_id),
                )
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

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
        self, conversation_id: str, *, user: str | None = None
    ) -> tuple[ConversationRef, list[dict[str, str]]] | None:
        """Ein Gespräch samt Nachrichten — optional auf einen Nutzer beschränkt.

        ``user`` ist der Schlüssel gegen den Fund aus dem Review: die Liste im
        Verlauf filterte nach Nutzer, die Handler dahinter nahmen die ID aber
        ungeprüft entgegen. Ein fremdes Gespräch sieht so aus wie ein nicht
        existierendes — bewusst, damit die Antwort nicht verrät, dass es die ID
        gibt. Terminal und API rufen weiter ohne ``user`` und sehen alles.
        """
        query = (
            "SELECT c.*, (SELECT COUNT(*) FROM messages m "
            "             WHERE m.conversation_id = c.id) AS message_count "
            "FROM conversations c WHERE c.id = ?"
        )
        params: list[Any] = [conversation_id]
        if user:
            query += " AND c.user = ?"
            params.append(user)
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
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

    def delete(self, conversation_id: str, *, user: str | None = None) -> bool:
        """Löscht ein Gespräch — optional nur, wenn es dem Nutzer gehört.

        Der Löschpfad ist der Grund, warum ``user`` kein optionaler Komfort ist:
        er ist unwiderruflich.
        """
        query = "DELETE FROM conversations WHERE id = ?"
        params: list[Any] = [conversation_id]
        if user:
            query += " AND user = ?"
            params.append(user)
        with self._lock:
            cursor = self._conn.execute(query, params)
            self._conn.commit()
            return cursor.rowcount > 0

    def search(
        self, query: str, *, user: str | None = None, limit: int = 50
    ) -> list[SearchHit]:
        """Volltextsuche über die eigenen Gespräche (#49).

        ``user`` wirkt wie bei ``load``/``delete``: gesetzt, sieht man nur die
        eigenen Fundstellen. Die WebUI **muss** ihn setzen, Terminal und API
        rufen ohne.
        """
        match = _fts_query(query)
        if not match:
            return []
        if not self._searchable:
            # Die Datei ist auf Version 1 stehengeblieben, weil dieses SQLite
            # kein FTS5 hat. Kein Fehler, nur nichts zu finden — die Meldung
            # gehört an die Oberfläche, nicht in einen Stacktrace.
            logging.info("[STORE] Suche nicht verfügbar: kein FTS5-Index angelegt")
            return []

        sql = (
            "SELECT c.id AS conversation_id, c.persona, c.updated_at, c.title, "
            "       m.role, m.idx, "
            "       snippet(messages_fts, 0, '»', '«', '…', 12) AS snippet "
            "FROM messages_fts "
            "JOIN messages m ON m.rowid = messages_fts.rowid "
            "JOIN conversations c ON c.id = m.conversation_id "
            "WHERE messages_fts MATCH ? "
        )
        params: list[Any] = [match]
        if user:
            sql += "AND c.user = ? "
            params.append(user)
        sql += "ORDER BY rank LIMIT ?"
        params.append(int(limit))

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            SearchHit(
                conversation_id=row["conversation_id"],
                persona=row["persona"],
                updated_at=row["updated_at"],
                title=row["title"],
                role=row["role"],
                idx=int(row["idx"]),
                snippet=row["snippet"],
            )
            for row in rows
        ]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _make_title(content: str) -> str:
    text = " ".join((content or "").split())
    if len(text) <= _TITLE_MAX_CHARS:
        return text
    return text[:_TITLE_MAX_CHARS].rstrip() + " …"


def _fts_query(query: str) -> str:
    """Nutzereingabe in eine FTS5-Anfrage — jedes Wort als Phrase, UND-verknüpft.

    Roh durchgereicht ist die Eingabe **Syntax**, nicht Text: ein `"`, ein `*`
    oder ein `AND` an der falschen Stelle wirft einen ``OperationalError``, und
    der Nutzer bekäme einen Fehler statt „nichts gefunden". Jedes Wort wird
    deshalb gequotet (inneres `"` verdoppelt); mehrere Wörter stehen
    nebeneinander, was in FTS5 UND bedeutet — das ist, was ein Suchfeld tut.
    """
    terms = ['"' + word.replace('"', '""') + '"' for word in (query or "").split()]
    return " ".join(terms)


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
    path = str(cfg.get("path") or DEFAULT_STORE_PATH)
    try:
        store = SqliteStore(path)
    except sqlite3.Error as exc:
        # Eine kaputte Datei darf die App nicht am Start hindern — dann eben
        # ohne Ablage, aber laut.
        logging.error(
            "[STORE] Ablage '%s' nicht nutzbar (%s) — es wird nichts gespeichert.",
            path,
            exc,
        )
        return NullStore()
    # Beim Beenden sauber schließen: das schreibt den WAL-Inhalt in die
    # Datenbank zurück, statt ihn dem nächsten Start zu überlassen.
    atexit.register(store.close)
    return store
