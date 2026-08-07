"""Die Vote-Aufzeichnung (#40/#65) — ohne Gradio, ohne WebUI (#56).

Genau das ist der Gewinn der Herauslösung: bis hierher ging jede Aussage über
diese Logik durch ein `WebUI`-Objekt mitsamt Factory, Config und Session. Die
Regeln sind aber reine Datenfragen, und so lassen sie sich auch stellen.

Die Abdeckung durch die Oberfläche bleibt bestehen (`test_web_ui.py` ruft
weiter `_on_chat_like`) — sie prüft jetzt die *Naht*, nicht mehr die Regeln.
"""

import json
import logging
import os

from ui.feedback import (
    DEFAULT_VOTES_DIR,
    LEGACY_VOTES_DIR,
    FeedbackLog,
    adopt_legacy_votes,
    store_index_of,
)


def _bubble(role, text):
    return {"role": role, "content": text}


def _log(tmp_path, **kwargs):
    return FeedbackLog(str(tmp_path / "votes.jsonl"), **kwargs)


def _lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


# ---- Die Zählregel --------------------------------------------------------


def test_the_same_answer_twice_is_told_apart_by_position():
    history = [
        _bubble("user", "Erste?"),
        _bubble("assistant", "Ja."),
        _bubble("user", "Zweite?"),
        _bubble("assistant", "Ja."),
    ]
    assert store_index_of("Ja.", 3, history, list(history)) == 3
    assert store_index_of("Ja.", 1, history, list(history)) == 1


def test_notices_do_not_count_as_answers():
    """Beiwerk steht nie in der LLM-History — daran wird es erkannt."""
    history = [
        _bubble("user", "Frage"),
        _bubble("assistant", "🕵️ blättert im Archiv …"),
        _bubble("assistant", "Antwort"),
    ]
    llm = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert store_index_of("Antwort", 2, history, llm) == 1
    # Der Hinweis selbst ist keine Modellantwort und damit nicht zuordenbar.
    assert store_index_of("🕵️ blättert im Archiv …", 1, history, llm) is None


# ---- Was geschrieben wird — und was nicht ---------------------------------


def test_a_vote_carries_the_join_key(tmp_path):
    log = _log(tmp_path)
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={"persona": "DORIS", "model": "m1"},
        conversation_id="c-1",
    )

    vote = _lines(tmp_path / "votes.jsonl")[0]
    assert vote["conversation_id"] == "c-1"
    assert vote["message_index"] == 1
    assert vote["vote"] == "up"
    assert vote["question"] == "Frage"
    assert vote["persona"] == "DORIS"


def test_a_vote_on_a_notice_writes_nothing(tmp_path):
    log = _log(tmp_path)
    history = [
        _bubble("user", "Frage"),
        _bubble("assistant", "📰 blättert durch tagesschau …"),
        _bubble("assistant", "Antwort"),
    ]
    llm = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert not log.record(
        row=1,
        liked=False,
        value="📰 blättert durch tagesschau …",
        chat_history=history,
        llm_history=llm,
        meta={},
        conversation_id="c",
    )
    assert not (tmp_path / "votes.jsonl").exists()


def test_a_vote_on_the_own_question_writes_nothing(tmp_path):
    log = _log(tmp_path)
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert not log.record(
        row=0,
        liked=True,
        value="Frage",
        chat_history=history,
        llm_history=list(history),
        meta={},
        conversation_id="c",
    )


def test_an_undecipherable_index_writes_nothing(tmp_path):
    """Verwerfen statt raten — eine erfundene Zeile ist teurer als keine."""
    log = _log(tmp_path)
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert not log.record(
        row=(1, 1),  # die alte Paar-Koordinate
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={},
        conversation_id="c",
    )
    assert not (tmp_path / "votes.jsonl").exists()


def test_an_index_outside_the_history_writes_nothing(tmp_path):
    log = _log(tmp_path)
    assert not log.record(
        row=99,
        liked=True,
        value="Antwort",
        chat_history=[_bubble("assistant", "Antwort")],
        llm_history=[_bubble("assistant", "Antwort")],
        meta={},
        conversation_id="c",
    )


# ---- Die Ablage hat das letzte Wort ---------------------------------------


def test_the_store_wording_beats_the_display(tmp_path):
    """Gegen die Ablage wird spaeter gejoint, also gilt ihr Wortlaut."""
    log = _log(tmp_path, store_loader=lambda cid, idx: "Fassung aus der Ablage")
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={},
        conversation_id="c-1",
    )
    assert _lines(tmp_path / "votes.jsonl")[0]["answer"] == "Fassung aus der Ablage"


def test_a_broken_store_still_leaves_the_vote(tmp_path):
    """Ohne Anmeldung gibt es keine Ablage (#72) — der Vote bleibt trotzdem."""

    def _boom(conversation_id, index):
        raise KeyError("kein Gespräch")

    log = _log(tmp_path, store_loader=_boom)
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={},
        conversation_id="c-1",
    )
    assert _lines(tmp_path / "votes.jsonl")[0]["answer"] == "Antwort"


def test_a_failing_write_never_raises(tmp_path):
    """Ein Vote darf die Oberflaeche nie zerreissen."""
    log = FeedbackLog(str(tmp_path / "gibt-es-nicht" / "votes.jsonl"))
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert not log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={},
        conversation_id="c",
    )


def test_the_user_falls_back_instead_of_writing_nothing(tmp_path):
    log = _log(tmp_path, fallback_user=lambda: "notnagel")
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={},
        conversation_id="c",
    )
    assert _lines(tmp_path / "votes.jsonl")[0]["user"] == "notnagel"


# ---- Formen und Faelle, die aus test_web_ui.py hierher gehoeren (#56) ------


def test_the_shape_the_frontend_sends_back_is_understood(tmp_path):
    """Gradio 6 reicht `content` als **Liste von Teilen** zurueck (#61a).

    Daran fiel der Vote lautlos aus: der Text fand sich nie im LLM-Verlauf
    wieder, `message_index` blieb None, es wurde nichts geschrieben — ohne
    Fehler, ohne Warnung, ohne Zeile.
    """
    log = _log(tmp_path)
    history = [
        {
            "role": "user",
            "metadata": None,
            "content": [{"type": "text", "text": "Frage"}],
        },
        {
            "role": "assistant",
            "metadata": None,
            "content": [{"type": "text", "text": "Antwort"}],
        },
    ]
    llm = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    assert log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=llm,
        meta={},
        conversation_id="c",
    )
    vote = _lines(tmp_path / "votes.jsonl")[0]
    assert vote["message_index"] == 1
    assert vote["answer"] == "Antwort"
    assert vote["question"] == "Frage"


def test_a_notice_before_the_first_answer_does_not_shift_it(tmp_path):
    """Gegenprobe zur Zaehlregel an der *ersten* Antwort.

    Der Hinweis steht vor ihr, also liegt sie in der Anzeige auf 2 und in der
    Ablage auf 1. Ein Zaehler, der Hinweise mitzaehlt, traefe nur hier daneben
    — nicht bei der letzten Antwort.
    """
    log = _log(tmp_path)
    history = [
        _bubble("user", "Frage"),
        _bubble("assistant", "🕵️ blättert im Archiv …"),
        _bubble("assistant", "Erste Antwort"),
        _bubble("user", "Noch was"),
        _bubble("assistant", "Zweite Antwort"),
    ]
    llm = [
        _bubble("user", "Frage"),
        _bubble("assistant", "Erste Antwort"),
        _bubble("user", "Noch was"),
        _bubble("assistant", "Zweite Antwort"),
    ]

    log.record(
        row=2,
        liked=True,
        value="Erste Antwort",
        chat_history=history,
        llm_history=llm,
        meta={},
        conversation_id="c",
    )
    vote = _lines(tmp_path / "votes.jsonl")[0]
    assert vote["message_index"] == 1
    assert vote["answer"] == "Erste Antwort"


def test_two_votes_append_two_lines(tmp_path):
    """Append-only: eine Neubewertung haengt an, Verbraucher entdoppeln selbst."""
    log = _log(tmp_path)
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    for liked in (True, False):
        log.record(
            row=1,
            liked=liked,
            value="Antwort",
            chat_history=history,
            llm_history=list(history),
            meta={},
            conversation_id="c",
        )

    votes = _lines(tmp_path / "votes.jsonl")
    assert [v["vote"] for v in votes] == ["up", "down"]


def test_the_meta_user_wins_over_the_fallback(tmp_path):
    log = _log(tmp_path, fallback_user=lambda: "notnagel")
    history = [_bubble("user", "Frage"), _bubble("assistant", "Antwort")]

    log.record(
        row=1,
        liked=True,
        value="Antwort",
        chat_history=history,
        llm_history=list(history),
        meta={"user": "yulyen"},
        conversation_id="c",
    )
    assert _lines(tmp_path / "votes.jsonl")[0]["user"] == "yulyen"


# ---- Umzug aus dem Logverzeichnis ----------------------------------------
#
# Der Vote-Log liegt seit dieser Runde neben der Ablage statt in `logs/`
# (Begründung im Modulkopf von `ui/feedback.py`). Ein Pfadwechsel ohne Umzug
# verliert stillschweigend Daten — und genau diese Sorte Verlust meldet sich
# nie von selbst, sondern erst, wenn jemand die Trainingsdaten für #7
# zusammenstellt und die Hälfte fehlt.


def _write(path, *rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_an_existing_log_is_moved_out_of_the_log_directory(tmp_path):
    legacy = tmp_path / "logs" / "feedback_votes.jsonl"
    _write(legacy, {"vote": "up"})
    target = tmp_path / "data" / "feedback_votes.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)

    result = adopt_legacy_votes(str(target), legacy_dir=str(tmp_path / "logs"))

    assert result == str(target)
    assert not legacy.exists(), "die alte Datei muss weg sein, sonst zwei Wahrheiten"
    assert _lines(target) == [{"vote": "up"}]


def test_nothing_happens_without_an_old_file(tmp_path):
    target = tmp_path / "data" / "feedback_votes.jsonl"

    assert adopt_legacy_votes(str(target), legacy_dir=str(tmp_path / "logs")) == str(
        target
    )
    assert not target.exists(), "es wird nichts angelegt, was noch niemand braucht"


def test_two_existing_files_are_left_alone(tmp_path, caplog):
    """Zusammenführen wäre geraten, nicht gewusst — also Finger weg und laut sein."""
    legacy = tmp_path / "logs" / "feedback_votes.jsonl"
    _write(legacy, {"vote": "up"})
    target = tmp_path / "data" / "feedback_votes.jsonl"
    _write(target, {"vote": "down"})

    with caplog.at_level(logging.WARNING):
        result = adopt_legacy_votes(str(target), legacy_dir=str(tmp_path / "logs"))

    assert result == str(target)
    assert legacy.exists(), "nichts darf verschwinden"
    assert _lines(legacy) == [{"vote": "up"}]
    assert any("existieren beide" in r.getMessage() for r in caplog.records)


def test_a_failed_move_keeps_writing_to_the_old_place(tmp_path, monkeypatch, caplog):
    """Eine verlorene Bewertung ist teurer als ein unaufgeräumtes Verzeichnis."""
    legacy = tmp_path / "logs" / "feedback_votes.jsonl"
    _write(legacy, {"vote": "up"})
    target = tmp_path / "data" / "feedback_votes.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)

    def _boom(*_args, **_kwargs):
        raise OSError("Datei in Benutzung")

    monkeypatch.setattr(os, "replace", _boom)
    with caplog.at_level(logging.WARNING):
        result = adopt_legacy_votes(str(target), legacy_dir=str(tmp_path / "logs"))

    assert result == str(legacy)
    assert _lines(legacy) == [{"vote": "up"}]


def test_the_default_directory_is_not_the_log_directory():
    """Der eigentliche Punkt dieser Runde, als Zusicherung."""
    assert DEFAULT_VOTES_DIR == "data"
    assert LEGACY_VOTES_DIR == "logs"
