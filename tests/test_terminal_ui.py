from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from config.texts import Texts
from ui.terminal_ui import TerminalUI


def _create_terminal_ui() -> TerminalUI:
    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    catalog = Texts(language="de", locales_dir=locales_dir)
    dummy_config = SimpleNamespace(
        texts=catalog,
        t=catalog.format,
        core={"model_name": "dummy"},
        ui={"experimental": {"broadcast_mode": True}},
    )

    return TerminalUI(
        factory=None,
        config=dummy_config,
        keyword_finder=None,
        wiki_snippet_limit=0,
        max_wiki_snippets=0,
        wiki_mode=False,
        proxy_base="",
        wiki_timeout=0,
    )


def test_terminal_ui_start_menu_shows_ask_all_when_enabled(monkeypatch, capsys) -> None:
    ui = _create_terminal_ui()

    prompts = iter(["exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    ui._start_dialog_flow()

    out = capsys.readouterr().out
    assert ui.texts["terminal_start_menu_ask_all_option"] in out


def test_terminal_ui_trims_history_when_context_is_full(monkeypatch, capsys) -> None:
    ui = _create_terminal_ui()
    ui.bot = "LEAH"
    ui.streamer = SimpleNamespace(persona_options={"num_ctx": "128"})

    ui.history = [
        {"role": "system", "content": "Regeln"},
        {"role": "user", "content": "Alte Frage"},
        {"role": "assistant", "content": "Antwort"},
        {"role": "user", "content": "Neue Frage"},
    ]

    trimmed_history = ui.history[1:].copy()
    calls: dict[str, object] = {}

    def fake_context_near_limit(history, persona_options):  # type: ignore[no-redef]
        calls["context_called"] = True
        return True

    def fake_karl(messages, num_ctx):  # type: ignore[no-redef]
        calls["karl_args"] = (list(messages), num_ctx)
        return trimmed_history

    monkeypatch.setattr("ui.terminal_ui.context_near_limit", fake_context_near_limit)
    monkeypatch.setattr("ui.terminal_ui.karl_prepare_quick_and_dirty", fake_karl)

    ui._ensure_context_headroom()

    captured = capsys.readouterr()

    assert calls.get("context_called") is True
    assert calls["karl_args"][1] == 128
    assert ui.history == trimmed_history
    assert "Einen Moment: LEAH holt sich Latte Macchiato ..." in captured.out
    assert "Ältere Nachrichten wurden entfernt" in captured.out


def test_terminal_ui_broadcast_flag_hides_askall(monkeypatch, capsys) -> None:
    locales_dir = Path(__file__).resolve().parents[1] / "locales"
    catalog = Texts(language="de", locales_dir=locales_dir)
    dummy_config = SimpleNamespace(
        texts=catalog,
        t=catalog.format,
        core={"model_name": "dummy"},
        ui={"experimental": {"broadcast_mode": False}},
    )

    ui = TerminalUI(
        factory=SimpleNamespace(),
        config=dummy_config,
        keyword_finder=None,
        wiki_snippet_limit=0,
        max_wiki_snippets=0,
        wiki_mode=False,
        proxy_base="",
        wiki_timeout=0,
    )
    prompts = iter(["3", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(prompts))

    ui._start_dialog_flow()

    out = capsys.readouterr().out
    assert ui.texts["terminal_start_menu_ask_all_option"] not in out
    assert ui.texts["terminal_invalid_selection"] in out


def test_terminal_ui_run_ask_all_flow_calls_broadcast(monkeypatch, capsys) -> None:
    ui = _create_terminal_ui()
    ui.factory = SimpleNamespace()
    question = "Testfrage"

    monkeypatch.setattr("builtins.input", lambda _: question)

    def fake_broadcast(factory, question_input, on_token):  # type: ignore[no-redef]
        assert question_input == question
        on_token("LEAH", "Hallo")
        on_token("MAX", "Hi")

    monkeypatch.setattr("ui.terminal_ui.broadcast_to_ensemble", fake_broadcast)

    ui._run_ask_all_flow()

    out = capsys.readouterr().out
    assert ui.texts["terminal_askall_block_start"] in out
    assert ui.texts["terminal_askall_block_end"] in out
    assert "[LEAH]" in out
    assert "[MAX]" in out


def test_terminal_ui_run_ask_all_flow_requires_question(monkeypatch, capsys) -> None:
    ui = _create_terminal_ui()
    monkeypatch.setattr("builtins.input", lambda _: "")
    mock_broadcast = Mock()
    monkeypatch.setattr("ui.terminal_ui.broadcast_to_ensemble", mock_broadcast)

    ui._run_ask_all_flow()

    out = capsys.readouterr().out
    assert ui.texts["terminal_askall_missing_question"] in out
    mock_broadcast.assert_not_called()
