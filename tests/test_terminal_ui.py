from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock
import sys

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
    prompts = iter(["4", "exit"])
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


def test_terminal_ui_tts_uses_explicit_persona(monkeypatch) -> None:
    ui = _create_terminal_ui()
    ui.tts_auto_wav_enabled = True
    ui.bot = None
    ui.config = SimpleNamespace(language="de")
    ui.tts_cfg = {"enabled": True, "features": {"terminal_auto_create_wav": True}, "voices": {}}

    calls: dict[str, object] = {}

    fake_piper = ModuleType("tts.piper_tts")
    fake_audio = ModuleType("tts.audio_player")

    def fake_create_wav(text, persona, voices_dir, out_wav, tts_cfg, language):
        calls["create"] = {
            "text": text,
            "persona": persona,
            "voices_dir": str(voices_dir),
            "out_wav": str(out_wav),
            "language": language,
        }

    def fake_play_wav(path, block):
        calls["play"] = {"path": str(path), "block": block}

    fake_piper.create_wav = fake_create_wav
    fake_audio.play_wav = fake_play_wav
    monkeypatch.setitem(sys.modules, "tts.piper_tts", fake_piper)
    monkeypatch.setitem(sys.modules, "tts.audio_player", fake_audio)

    ui._maybe_create_tts_wav("Hallo Selftalk", block=True, persona_name="LEAH")

    assert calls["create"]["persona"] == "LEAH"
    assert calls["create"]["language"] == "de"
    assert calls["play"]["block"] is True


def test_terminal_ui_tts_skips_without_persona(monkeypatch) -> None:
    ui = _create_terminal_ui()
    ui.tts_auto_wav_enabled = True
    ui.bot = None

    create_mock = Mock()
    play_mock = Mock()

    fake_piper = ModuleType("tts.piper_tts")
    fake_audio = ModuleType("tts.audio_player")
    fake_piper.create_wav = create_mock
    fake_audio.play_wav = play_mock

    monkeypatch.setitem(sys.modules, "tts.piper_tts", fake_piper)
    monkeypatch.setitem(sys.modules, "tts.audio_player", fake_audio)

    ui._maybe_create_tts_wav("Hallo ohne Persona")

    create_mock.assert_not_called()
    play_mock.assert_not_called()
