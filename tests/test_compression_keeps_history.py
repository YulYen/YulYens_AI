"""Kontext-Kompression kürzt den *Prompt*, nicht das *Gespräch*.

Bis hierher war beides dieselbe Liste. Karl und der heuristische Trim
entfernten die ältesten Turns aus dem LLM-Verlauf, und weil die Oberfläche
genau diesen Verlauf in die Ablage spiegelt (``sync`` ersetzt, #59), verschwanden
sie dort mit: nach der ersten Kompression fehlte dem gespeicherten Gespräch der
Anfang, sein Titel wechselte auf eine spätere Frage, und Verlauf, Suche,
Markdown-Export und JSON-Download zeigten nur noch den Rest.

Die Tests hier laufen gegen die echte Ablage und den echten Streamer — der
Fehler lag im Zusammenspiel dreier Teile, die jeder für sich taten, was sie
sollten.
"""

from types import SimpleNamespace

import pytest
from core.context_injection import (
    conversation_only,
    is_compressed,
    prompt_only,
    recorded_turns,
)
from core.context_utils import approx_token_count, shrink_history_for_context
from core.dummy_llm_core import DummyLLMCore
from core.streaming_provider import YulYenStreamingProvider
from rss.feeds import RssCache
from storage.store import SqliteStore
from ui.feedback import store_index_of
from ui.session import SessionContext
from ui.webui_chat import ChatController
from wiki.lookup import WikiLookup

NUM_CTX = 1200
TURNS = 8


class RecordingCore(DummyLLMCore):
    """Echo-Backend, das sich merkt, was es als Prompt bekommen hat."""

    def __init__(self) -> None:
        self.prompts: list[list[dict]] = []

    def stream_chat(self, model_name, messages, options=None, keep_alive=600):
        # Karls Auftrag erkennt man an seiner Systemnachricht. Ein Echo wäre
        # dort keine Zusammenfassung, sondern der ganze Verlauf noch einmal.
        if messages and messages[0].get("content", "").startswith("Compress"):
            return iter([{"message": {"content": "Kurzfassung des Bisherigen."}}])
        self.prompts.append([dict(m) for m in messages])
        return super().stream_chat(model_name, messages, options, keep_alive)


def _cfg(strategy, tmp_path):
    return SimpleNamespace(
        core={},
        context_management={
            "strategy": strategy,
            "karl": {
                "model": "same_as_chat",
                "summary_max_tokens": 64,
                "keep_last_messages": 2,
                "log_dir": str(tmp_path / "karl"),
            },
        },
    )


def _question(index: int) -> str:
    return f"Frage {index}: " + "bla " * 60


def _chat_through_the_webui(strategy, tmp_path):
    store = SqliteStore(tmp_path / "c.sqlite3")
    core = RecordingCore()
    streamer = YulYenStreamingProvider(
        "", "LEAH", "", {"num_ctx": NUM_CTX}, llm_core=core, store=store
    )
    conversation_id = store.start(user="yul", persona="LEAH", model="m", app="web")
    streamer.set_conversation(conversation_id)
    session = SessionContext(bot="LEAH", streamer=streamer)
    chat = ChatController(
        lambda key, **_kwargs: key,
        _cfg(strategy, tmp_path),
        WikiLookup(),
        RssCache(feeds=[]),
    )

    history: list[dict] = []
    bubbles: list[dict] = []
    for index in range(TURNS):
        for out in chat.respond_streaming(session, _question(index), bubbles, history):
            history = out[2]
    return store, conversation_id, history, bubbles, core


@pytest.mark.parametrize("strategy", ["heuristic", "karl"])
def test_the_stored_conversation_keeps_its_beginning(strategy, tmp_path):
    store, conversation_id, _history, _bubbles, _core = _chat_through_the_webui(
        strategy, tmp_path
    )

    ref, stored = store.load(conversation_id)

    assert [m["role"] for m in stored] == ["user", "assistant"] * TURNS
    assert [m["content"][:8] for m in stored[::2]] == [
        f"Frage {index}:" for index in range(TURNS)
    ]
    assert ref.title.startswith("Frage 0:")


@pytest.mark.parametrize("strategy", ["heuristic", "karl"])
def test_the_prompt_is_still_compressed(strategy, tmp_path):
    """Die Gegenprobe: behalten heißt nicht, wieder alles ans Modell zu schicken."""
    _store, _cid, history, _bubbles, core = _chat_through_the_webui(strategy, tmp_path)

    last_prompt = core.prompts[-1]
    assert not any("Frage 0:" in m["content"] for m in last_prompt)
    assert any(f"Frage {TURNS - 1}:" in m["content"] for m in last_prompt)
    assert not any(is_compressed(m) for m in last_prompt)
    # Der Füllstand zählt, was gesendet wird — sonst komprimierte jeder Turn neu.
    assert approx_token_count(history) < NUM_CTX
    assert approx_token_count(history) == approx_token_count(prompt_only(history))


def test_a_vote_still_points_at_the_right_stored_message(tmp_path):
    """Ablage und Zählregel müssen nach der Kompression dieselbe Folge sehen."""
    store, conversation_id, history, bubbles, _core = _chat_through_the_webui(
        "heuristic", tmp_path
    )
    _ref, stored = store.load(conversation_id)

    for row, bubble in enumerate(bubbles):
        if bubble["role"] != "assistant" or not bubble["content"].startswith("ECHO"):
            continue
        index = store_index_of(bubble["content"], row, bubbles, history)
        assert index is not None, "auch eine alte Antwort bleibt bewertbar"
        assert stored[index]["content"] == bubble["content"]


def test_shrinking_marks_instead_of_dropping():
    history = [
        {"role": "user", "content": "alt " * 200},
        {"role": "assistant", "content": "Antwort " * 200},
        {"role": "user", "content": "neu"},
        {"role": "assistant", "content": "ja"},
    ]
    cfg = SimpleNamespace(context_management={"strategy": "heuristic"})

    result = shrink_history_for_context(
        history, cfg, {"num_ctx": 600}, llm_core=None, chat_model_name=""
    )

    assert [m["content"] for m in recorded_turns(result)] == [
        m["content"] for m in history
    ]
    assert [m["content"] for m in prompt_only(result)] == ["neu", "ja"]
    # Der Aufrufer behält seine Liste: markiert wird eine Kopie.
    assert not any(is_compressed(m) for m in history)


def test_an_export_does_not_carry_the_marker():
    """Die Datei ist das Gespräch — der Prompt-Zustand gehört nicht hinein."""
    from core.context_injection import COMPRESSED_KEY

    history = [{"role": "user", "content": "alt", COMPRESSED_KEY: True}]

    assert conversation_only(history) == [{"role": "user", "content": "alt"}]


def test_the_terminal_keeps_the_whole_conversation_too(tmp_path, monkeypatch):
    """Derselbe Weg im Terminal: `_ensure_context_headroom`, dann aufzeichnen."""
    from pathlib import Path

    from config.texts import Texts
    from ui.terminal_ui import TerminalUI

    catalog = Texts(
        language="de", locales_dir=Path(__file__).resolve().parents[1] / "locales"
    )
    cfg = _cfg("heuristic", tmp_path)
    cfg.texts, cfg.t, cfg.ui = catalog, catalog.format, {}
    monkeypatch.setattr("ui.terminal_ui.get_drink", lambda _name: "Tee")
    store = SqliteStore(tmp_path / "t.sqlite3")
    ui = TerminalUI(factory=None, config=cfg, wiki=WikiLookup())
    ui.bot = "LEAH"
    ui.streamer = YulYenStreamingProvider(
        "", "LEAH", "", {"num_ctx": NUM_CTX}, llm_core=DummyLLMCore(), store=store
    )
    conversation_id = store.start(user="local", persona="LEAH", model="m", app="t")
    ui.streamer.set_conversation(conversation_id)

    for index in range(TURNS):
        ui.history.append({"role": "user", "content": _question(index)})
        ui._ensure_context_headroom()
        ui._stream_and_record_reply()

    _ref, stored = store.load(conversation_id)
    assert len(stored) == 2 * TURNS
    assert stored[0]["content"].startswith("Frage 0:")
    assert len(prompt_only(ui.history)) < len(ui.history)
