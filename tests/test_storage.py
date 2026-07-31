"""Ablage der Gespräche (#54).

Der Store ersetzt den Missbrauch des Logfiles als Persistenz. Geprüft wird
deshalb vor allem, was das Logfile *nicht* konnte: Gespräche als eigenständige
Objekte, Filtern nach Nutzer, und ein Schema, das sich weiterentwickeln lässt.
"""

import sqlite3

import pytest
from storage import NullStore, SqliteStore, build_store
from storage.store import _MIGRATIONS


@pytest.fixture()
def store(tmp_path):
    return SqliteStore(tmp_path / "conversations.sqlite3")


def test_conversation_round_trip(store):
    cid = store.start(user="yulyen", persona="LEAH", model="m1", app="web")
    store.append(cid, "user", "Hallo")
    store.append(cid, "assistant", "Moin")

    ref, messages = store.load(cid)

    assert ref.persona == "LEAH"
    assert ref.user == "yulyen"
    assert ref.message_count == 2
    assert messages == [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Moin"},
    ]


def test_title_comes_from_the_first_question(store):
    cid = store.start(user="u", persona="P", model="m", app="web")
    store.append(cid, "user", "Was ist die Hauptstadt von Deutschland?")
    store.append(cid, "assistant", "Berlin.")

    assert (
        store.list_conversations()[0].title == "Was ist die Hauptstadt von Deutschland?"
    )


def test_long_titles_are_shortened(store):
    cid = store.start(user="u", persona="P", model="m", app="web")
    store.append(cid, "user", "wort " * 100)

    title = store.list_conversations()[0].title
    assert len(title) <= 82 and title.endswith("…")


def test_list_only_returns_the_given_users_conversations(store):
    """Genau dafür kam #53 vorher — sonst sieht im Verlauf jeder alles."""
    mine = store.start(user="yulyen", persona="LEAH", model="m", app="web")
    store.start(user="jemand_anders", persona="DORIS", model="m", app="web")

    ids = [ref.id for ref in store.list_conversations(user="yulyen")]

    assert ids == [mine]
    assert len(store.list_conversations()) == 2  # ohne Filter beide


def test_list_is_ordered_by_last_activity(store):
    first = store.start(user="u", persona="A", model="m", app="web")
    second = store.start(user="u", persona="B", model="m", app="web")
    store.append(first, "user", "später angefasst")

    assert [ref.id for ref in store.list_conversations()][0] == first
    assert second in [ref.id for ref in store.list_conversations()]


def test_delete_removes_the_conversation_and_its_messages(store):
    cid = store.start(user="u", persona="P", model="m", app="web")
    store.append(cid, "user", "Hallo")

    assert store.delete(cid) is True
    assert store.load(cid) is None
    assert store.list_conversations() == []
    # ON DELETE CASCADE: keine verwaisten Nachrichten
    rows = store._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert rows == 0


def test_delete_of_an_unknown_id_is_not_an_error(store):
    assert store.delete("gibtesnicht") is False


def test_load_of_an_unknown_id_returns_none(store):
    assert store.load("gibtesnicht") is None


def test_append_without_a_conversation_is_ignored(store):
    """Ein Streamer ohne gesetztes Gespräch darf nichts kaputt machen."""
    store.append("", "user", "ins Leere")

    assert store.list_conversations() == []


def test_user_defaults_to_local_when_empty(store):
    cid = store.start(user="", persona="P", model="m", app="terminal")

    assert store.load(cid)[0].user == "local"


# ---- Schema und Migrationen -------------------------------------------------


def test_schema_is_migrated_and_reopening_is_idempotent(tmp_path):
    path = tmp_path / "conversations.sqlite3"
    first = SqliteStore(path)
    cid = first.start(user="u", persona="P", model="m", app="web")
    first.close()

    second = SqliteStore(path)

    version = second._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(_MIGRATIONS)
    assert [ref.id for ref in second.list_conversations()] == [cid]


def test_migration_starts_from_an_empty_file(tmp_path):
    path = tmp_path / "leer.sqlite3"
    sqlite3.connect(str(path)).close()  # existiert, aber ohne Schema

    store = SqliteStore(path)

    assert store.list_conversations() == []


# ---- NullStore und Konfiguration -------------------------------------------


def test_null_store_swallows_everything(tmp_path):
    store = NullStore()

    assert store.start(user="u", persona="P", model="m", app="web") == ""
    store.append("egal", "user", "text")
    assert store.list_conversations() == []
    assert store.load("egal") is None
    assert store.delete("egal") is False
    assert not list(tmp_path.iterdir())


def test_build_store_honours_the_switch(tmp_path):
    assert isinstance(build_store({"enabled": False}), NullStore)
    built = build_store({"enabled": True, "path": str(tmp_path / "db.sqlite3")})
    assert isinstance(built, SqliteStore)


def test_build_store_degrades_instead_of_blocking_the_start(tmp_path, caplog):
    """Eine unbrauchbare Datei darf die App nicht am Start hindern."""
    blocked = tmp_path / "verzeichnis.sqlite3"
    blocked.mkdir()

    store = build_store({"enabled": True, "path": str(blocked)})

    assert isinstance(store, NullStore)
    assert "nicht nutzbar" in caplog.text


# ---- Alle Kanäle zeichnen auf (#54) ----------------------------------------
# Vorher hing die Aufzeichnung am JSONL-Mitschnitt; seit der aus ist, muss jeder
# Kanal ein Gespräch eröffnen — sonst schreibt er ins Leere.


def test_factory_opens_a_conversation_for_any_channel(tmp_path, monkeypatch):
    from config.config_singleton import Config
    from core.factory import AppFactory

    Config.reset_instance()
    try:
        cfg = Config("config.yaml")
        cfg.ensemble = "classic"
        cfg.override("core", {"backend": "dummy"})
        factory = AppFactory()
        store = SqliteStore(tmp_path / "conversations.sqlite3")
        monkeypatch.setattr(factory, "get_store", lambda: store)

        cid = factory.open_conversation("PETER", "terminal")

        ref, _messages = store.load(cid)
        assert ref.app == "terminal"
        assert ref.user == "local"  # ohne Anmeldung die ehrliche Antwort
    finally:
        Config.reset_instance()


def test_open_conversation_never_breaks_the_caller(tmp_path, monkeypatch, caplog):
    """Ein kaputter Store darf kein Gespräch verhindern, nur keins aufzeichnen."""
    from config.config_singleton import Config
    from core.factory import AppFactory

    class _Broken:
        def start(self, **_kwargs):
            raise RuntimeError("Platte voll")

    Config.reset_instance()
    try:
        cfg = Config("config.yaml")
        cfg.ensemble = "classic"
        cfg.override("core", {"backend": "dummy"})
        factory = AppFactory()
        monkeypatch.setattr(factory, "get_store", lambda: _Broken())

        assert factory.open_conversation("PETER", "api") == ""
        assert "nicht angelegt" in caplog.text
    finally:
        Config.reset_instance()
