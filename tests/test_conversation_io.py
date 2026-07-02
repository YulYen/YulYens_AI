import json

import pytest
from ui.conversation_io_terminal import load_conversation, save_conversation

META = {
    "created_at": "2026-07-02T10:00:00",
    "model": "dummy",
    "persona": "LEAH",
    "app": "terminal",
}

MESSAGES = [
    {"role": "user", "content": "Hallo"},
    {"role": "assistant", "content": "Hi!"},
]


def test_save_and_load_roundtrip(tmp_path):
    target = tmp_path / "conv.json"
    save_conversation(str(target), META, MESSAGES)

    meta, messages = load_conversation(str(target))

    assert meta == META
    assert messages == MESSAGES


def test_save_rejects_invalid_types(tmp_path):
    target = tmp_path / "conv.json"
    with pytest.raises(ValueError, match="meta"):
        save_conversation(str(target), "kein dict", MESSAGES)
    with pytest.raises(ValueError, match="messages"):
        save_conversation(str(target), META, "keine liste")


def test_load_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_conversation(str(tmp_path / "nope.json"))


def test_load_rejects_invalid_json(tmp_path):
    target = tmp_path / "conv.json"
    target.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_conversation(str(target))


def test_load_rejects_non_object_top_level(tmp_path):
    target = tmp_path / "conv.json"
    target.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError, match="'meta' and 'messages'"):
        load_conversation(str(target))


@pytest.mark.parametrize(
    "broken_meta, expected",
    [
        (None, "missing required object 'meta'"),
        ({"model": "m", "persona": "p", "app": "a"}, "created_at"),
        ({**META, "persona": ""}, "non-empty string"),
        ({**META, "model": 42}, "non-empty string"),
    ],
)
def test_load_rejects_broken_meta(tmp_path, broken_meta, expected):
    target = tmp_path / "conv.json"
    target.write_text(
        json.dumps({"meta": broken_meta, "messages": MESSAGES}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=expected):
        load_conversation(str(target))


@pytest.mark.parametrize(
    "broken_messages, expected",
    [
        (None, "missing required list 'messages'"),
        (["kein dict"], "Message #1"),
        ([{"role": "user"}], "Message #1"),
        ([{"role": "user", "content": 5}], "Message #1"),
        (MESSAGES + [{"role": 1, "content": "x"}], "Message #3"),
    ],
)
def test_load_rejects_broken_messages(tmp_path, broken_messages, expected):
    target = tmp_path / "conv.json"
    target.write_text(
        json.dumps({"meta": META, "messages": broken_messages}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match=expected):
        load_conversation(str(target))


def test_load_normalizes_messages_to_role_and_content(tmp_path):
    target = tmp_path / "conv.json"
    noisy = [{"role": "user", "content": "Hallo", "extra": "wird verworfen"}]
    target.write_text(json.dumps({"meta": META, "messages": noisy}), encoding="utf-8")

    _, messages = load_conversation(str(target))

    assert messages == [{"role": "user", "content": "Hallo"}]
