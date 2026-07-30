"""Tests for the WebUI-specific server configuration."""

import json
import logging
import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import Mock, patch

import gradio as gr
import requests
from config.texts import Texts
from ui.web_ui import PERSONA_OUTPUT_KEYS, STREAM_OUTPUT_KEYS, WebUI
from wiki.lookup import WikiSnippet


def test_webui_start_server_uses_configured_host_and_port():
    """`demo.launch` must be called with the configured host/port values."""

    dummy_config = SimpleNamespace(texts={}, t=lambda key, **kwargs: key)

    web_ui = WebUI(
        factory=Mock(),
        config=dummy_config,
        keyword_finder=Mock(),
        wiki_snippet_limit=42,
        max_wiki_snippets=2,
        wiki_mode="offline",
        proxy_port=8042,
        web_host="0.0.0.0",
        web_port="9000",
        wiki_timeout=1.0,
    )

    demo = Mock()

    web_ui._start_server(demo)

    demo.launch.assert_called_once_with(
        server_name="0.0.0.0", server_port=9000, show_api=False
    )


def _create_web_ui(ui_config=None):
    if ui_config is None:
        ui_config = {"experimental": {"broadcast_mode": True}}

    dummy_config = SimpleNamespace(
        texts={},
        t=lambda key, **kwargs: key,
        ui=ui_config,
        context_management={
            "strategy": "heuristic",
            "karl": {
                "model": "same_as_chat",
                "summary_max_tokens": 512,
                "keep_last_messages": 2,
                "log_dir": "logs",
            },
        },
    )
    return WebUI(
        factory=Mock(),
        config=dummy_config,
        keyword_finder=None,
        wiki_snippet_limit=42,
        max_wiki_snippets=2,
        wiki_mode="offline",
        proxy_port=8042,
        web_host="0.0.0.0",
        web_port="9000",
        wiki_timeout=1.0,
    )


def test_stream_reply_throttles_updates():
    """Tokens are coalesced: far fewer yields than tokens, full text at the end."""

    web_ui = _create_web_ui()
    tokens = [f"t{i} " for i in range(50)]
    full_text = "".join(tokens)
    streamer = Mock()
    streamer.stream.return_value = iter(tokens)
    web_ui.streamer = streamer

    # 10 ms per token → with the 0.1 s throttle only every ~10th token flushes.
    clock = iter(1000.0 + i * 0.01 for i in range(len(tokens) + 5))
    with patch("ui.web_ui.time.monotonic", side_effect=lambda: next(clock)):
        outputs = list(web_ui._stream_reply([], []))

    assert len(outputs) < len(tokens) / 2
    final_chat = outputs[-1][1]
    assert final_chat[-1] == (None, full_text)


def test_stream_reply_always_flushes_final_state():
    """Even if the throttle suppresses every update, the final yield is complete."""

    web_ui = _create_web_ui()
    tokens = ["Hallo ", "Welt", "!"]
    streamer = Mock()
    streamer.stream.return_value = iter(tokens)
    web_ui.streamer = streamer

    # Frozen clock: after the first flush no throttle window ever elapses.
    with patch("ui.web_ui.time.monotonic", return_value=1000.0):
        outputs = list(web_ui._stream_reply([], []))

    final_chat = outputs[-1][1]
    assert final_chat[-1] == (None, "Hallo Welt!")
    assert outputs[-1][2][-1] == {"role": "assistant", "content": "Hallo Welt!"}


def test_respond_streaming_prepares_history_with_valid_num_ctx():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {"num_ctx": "4096"}
    streamer.stream.return_value = iter(["Hallo"])
    web_ui.streamer = streamer

    chat_history = []
    history_state = []

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.inject_wiki_context"),
        patch("ui.web_ui.context_near_limit", return_value=True),
        patch("ui.web_ui.get_drink", return_value="☕"),
        patch(
            "core.context_utils.karl_prepare_quick_and_dirty",
            side_effect=lambda history, limit: history,
        ) as mock_prepare,
    ):
        list(web_ui.respond_streaming("Hallo", chat_history, history_state))

    mock_prepare.assert_called_once()
    assert mock_prepare.call_args[0][1] == 4096
    streamer.stream.assert_called_once()


def test_webui_heuristic_strategy_never_instantiates_karl():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {"num_ctx": "4096"}
    streamer.stream.return_value = iter(["Hallo"])
    web_ui.streamer = streamer

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.context_near_limit", return_value=True),
        patch("ui.web_ui.get_drink", return_value="☕"),
        patch(
            "core.context_utils.karl_prepare_quick_and_dirty",
            side_effect=lambda h, c: h,
        ),
        patch("core.context_utils.KarlSummarizer") as mock_karl,
    ):
        list(web_ui.respond_streaming("Hallo", [], []))

    mock_karl.assert_not_called()


def test_webui_karl_strategy_uses_karl_instead_of_heuristic():
    web_ui = _create_web_ui()
    web_ui.cfg.context_management["strategy"] = "karl"
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {"num_ctx": "4096"}
    streamer.model_name = "chat-model"
    streamer._llm_core = Mock()
    streamer.stream.return_value = iter(["Antwort"])
    web_ui.streamer = streamer

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.context_near_limit", return_value=True),
        patch("ui.web_ui.get_drink", return_value="☕"),
        patch("core.context_utils.karl_prepare_quick_and_dirty") as mock_prepare,
        patch("core.context_utils.KarlSummarizer") as mock_karl,
    ):
        instance = mock_karl.return_value
        instance.summarize.return_value = [{"role": "system", "content": "S"}]
        outputs = list(web_ui.respond_streaming("Hallo", [], []))

    mock_prepare.assert_not_called()
    mock_karl.assert_called_once()
    final_state = outputs[-1][2]
    assert final_state[0] == {"role": "system", "content": "S"}


def test_respond_streaming_skips_history_preparation_without_num_ctx(caplog):
    caplog.set_level(logging.DEBUG)

    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {}
    streamer.stream.return_value = iter(["Hallo"])
    web_ui.streamer = streamer

    chat_history = []
    history_state = []

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.inject_wiki_context"),
        patch("ui.web_ui.context_near_limit", return_value=True),
        patch("ui.web_ui.get_drink", return_value="☕"),
        patch("core.context_utils.karl_prepare_quick_and_dirty") as mock_prepare,
    ):
        list(web_ui.respond_streaming("Hallo", chat_history, history_state))

    mock_prepare.assert_not_called()
    assert "Skipping 'karl_prepare_quick_and_dirty'" in caplog.text
    streamer.stream.assert_called_once()


def test_respond_streaming_keeps_session_histories_isolated():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {}
    responses = [["Antwort 1"], ["Antwort 2"]]
    captured_messages = []

    def stream_side_effect(*args, **kwargs):
        messages = kwargs["messages"]
        captured_messages.append([msg.copy() for msg in messages])
        return iter(responses.pop(0))

    streamer.stream.side_effect = stream_side_effect
    web_ui.streamer = streamer

    session_one_state = []
    session_two_state = []

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.context_near_limit", return_value=False),
    ):
        session_one_outputs = list(
            web_ui.respond_streaming("Frage 1", [], session_one_state)
        )
        session_two_outputs = list(
            web_ui.respond_streaming("Frage 2", [], session_two_state)
        )

    final_history_one = session_one_outputs[-1][2]
    final_history_two = session_two_outputs[-1][2]

    assert session_one_state == []
    assert session_two_state == []
    assert captured_messages == [
        [{"role": "user", "content": "Frage 1"}],
        [{"role": "user", "content": "Frage 2"}],
    ]
    assert final_history_one == [
        {"role": "user", "content": "Frage 1"},
        {"role": "assistant", "content": "Antwort 1"},
    ]
    assert final_history_two == [
        {"role": "user", "content": "Frage 2"},
        {"role": "assistant", "content": "Antwort 2"},
    ]
    assert final_history_one is not final_history_two


def test_respond_streaming_returns_chat_and_state_updates():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {}
    streamer.stream.return_value = iter(["Hi"])
    web_ui.streamer = streamer

    chat_history: list = []
    history_state: list = []

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.context_near_limit", return_value=False),
    ):
        outputs = list(web_ui.respond_streaming("Hallo", chat_history, history_state))

    assert outputs
    assert all(len(item) == len(STREAM_OUTPUT_KEYS) for item in outputs)
    assert chat_history[-1] == (None, "Hi")
    assert history_state == []


def test_respond_streaming_appends_final_history_entries():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    chat_history: list = []
    history_state: list = []

    streamer = Mock()
    streamer.persona_options = {}
    streamer.stream.return_value = iter(["Hallo"])
    web_ui.streamer = streamer

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.context_near_limit", return_value=False),
    ):
        outputs = list(web_ui.respond_streaming("Hallo", chat_history, history_state))

    final_state = outputs[-1][2]
    assert final_state == [
        {"role": "user", "content": "Hallo"},
        {"role": "assistant", "content": "Hallo"},
    ]


def test_on_submit_ask_all_injects_wiki_context_and_shows_hints():
    web_ui = _create_web_ui()
    captured: dict = {}

    def fake_iter_broadcast_events(
        factory, question, *, context_messages=None, stop_event=None
    ):
        captured["context_messages"] = list(context_messages or [])
        yield {"type": "done", "persona": "LEAH", "reply": "Antwort"}

    def fake_inject(history, contexts):
        history.append({"role": "system", "content": "WIKI"})

    with (
        patch("ui.web_ui.get_all_persona_names", return_value=["LEAH"]),
        patch(
            "ui.web_ui.lookup_wiki_snippet",
            return_value=(["🕵️ Hinweis"], [WikiSnippet("Thema", "Snippet")]),
        ) as mock_lookup,
        patch("ui.web_ui.inject_wiki_context", side_effect=fake_inject),
        patch(
            "ui.web_ui.iter_broadcast_events_parallel",
            side_effect=fake_iter_broadcast_events,
        ),
    ):
        outputs = list(web_ui._on_submit_ask_all("Frage"))

    # Lookup läuft genau einmal (nicht pro Persona), Kontext erreicht den Broadcast
    mock_lookup.assert_called_once()
    assert captured["context_messages"] == [{"role": "system", "content": "WIKI"}]

    # Der Wiki-Hint landet im Status-Feld (Index 1 des Ask-All-Update-Tupels)
    final_status = outputs[-1][1]
    assert final_status["value"] == "🕵️ Hinweis"
    assert final_status["visible"] is True


def test_on_submit_ask_all_without_wiki_hits_sends_empty_context():
    web_ui = _create_web_ui()
    captured: dict = {}

    def fake_iter_broadcast_events(
        factory, question, *, context_messages=None, stop_event=None
    ):
        captured["context_messages"] = list(context_messages or [])
        yield {"type": "done", "persona": "LEAH", "reply": "Antwort"}

    with (
        patch("ui.web_ui.get_all_persona_names", return_value=["LEAH"]),
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch(
            "ui.web_ui.iter_broadcast_events_parallel",
            side_effect=fake_iter_broadcast_events,
        ),
    ):
        outputs = list(web_ui._on_submit_ask_all("Frage"))

    assert captured["context_messages"] == []
    final_status = outputs[-1][1]
    assert final_status["visible"] is False


def test_reset_to_start_cancels_running_ask_all_broadcast():
    web_ui = _create_web_ui()
    stop = threading.Event()
    web_ui._ask_all_stop = stop

    web_ui._on_reset_to_start()

    assert stop.is_set()
    assert web_ui._ask_all_stop is None


def test_on_submit_ask_all_sequential_fallback_via_config():
    web_ui = _create_web_ui(
        ui_config={
            "experimental": {"broadcast_mode": True, "broadcast_parallel": False}
        }
    )

    def fake_iter_broadcast_events(factory, question, *, context_messages=None):
        yield {"type": "done", "persona": "LEAH", "reply": "Antwort"}

    with (
        patch("ui.web_ui.get_all_persona_names", return_value=["LEAH"]),
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch(
            "ui.web_ui.iter_broadcast_events",
            side_effect=fake_iter_broadcast_events,
        ) as mock_sequential,
        patch("ui.web_ui.iter_broadcast_events_parallel") as mock_parallel,
    ):
        outputs = list(web_ui._on_submit_ask_all("Frage"))

    mock_sequential.assert_called_once()
    mock_parallel.assert_not_called()
    assert "Antwort" in outputs[-1][2]["value"]


def test_on_start_self_talk_validates_distinct_personas():
    web_ui = _create_web_ui()

    updates = web_ui._on_start_self_talk("Karl", "Karl", "Los geht's")

    assert updates[0]["visible"] is True


def test_run_self_talk_stream_yields_alternating_messages():
    web_ui = _create_web_ui()

    runner = Mock()
    runner.run_turn.side_effect = [
        ("Karl", "Hallo", False, 1),
        ("Yul", "Hi", True, 2),
    ]
    web_ui.self_talk_runner = runner

    outputs = list(web_ui._run_self_talk_stream([], []))

    assert outputs
    final_chat, final_state = outputs[-1]
    assert final_chat[-2:] == [(None, "Karl: Hallo"), (None, "Yul: Hi")]
    assert final_state[-2:] == [
        {"role": "assistant", "content": "Karl: Hallo"},
        {"role": "assistant", "content": "Yul: Hi"},
    ]


def test_on_show_self_talk_returns_expected_output_count_and_enables_setup():
    web_ui = _create_web_ui()

    updates = web_ui._on_show_self_talk()

    assert len(updates) == len(PERSONA_OUTPUT_KEYS)
    assert updates[22]["visible"] is True
    assert updates[27]["interactive"] is True


def test_load_failure_updates_sets_load_status_slot():
    web_ui = _create_web_ui()

    updates = web_ui._load_failure_updates("load failed")

    assert updates[21]["value"] == "load failed"
    assert updates[21]["visible"] is True


def test_on_start_self_talk_clears_stale_runner_on_validation_error():
    web_ui = _create_web_ui()
    web_ui.self_talk_runner = Mock()

    web_ui._on_start_self_talk("Karl", "Karl", "Prompt")

    assert web_ui.self_talk_runner is None


# ---- Modell-Auswahl (Profi-Option, #6) -------------------------------------


def test_available_models_falls_back_to_default_when_ollama_down():
    web_ui = _create_web_ui()
    web_ui.cfg.core = {"backend": "ollama", "ollama_url": "http://x:1"}

    with patch(
        "ui.web_ui.fetch_model_names",
        side_effect=requests.ConnectionError("refused"),
    ):
        assert web_ui._available_models("standard:1") == ["standard:1"]


def test_available_models_unions_default_first():
    web_ui = _create_web_ui()
    web_ui.cfg.core = {"backend": "ollama", "ollama_url": "http://x:1"}

    with patch("ui.web_ui.fetch_model_names", return_value=["a:1", "b:2"]):
        choices = web_ui._available_models("standard:1")

    assert choices == ["standard:1", "a:1", "b:2"]


def test_available_models_dummy_backend_skips_request():
    web_ui = _create_web_ui()
    web_ui.cfg.core = {"backend": "dummy"}

    with patch("ui.web_ui.fetch_model_names") as mock_fetch:
        assert web_ui._available_models("standard:1") == ["standard:1"]

    mock_fetch.assert_not_called()


def test_on_model_selected_overrides_config_and_rebuilds_streamer():
    web_ui = _create_web_ui()
    web_ui.cfg.override = Mock()
    web_ui.bot = "Karl"

    update = web_ui._on_model_selected("neu:1")

    web_ui.cfg.override.assert_called_once_with("core", {"model_name": "neu:1"})
    web_ui.factory.get_streamer_for_persona.assert_called_once_with("Karl")
    assert update["visible"] is True


def test_on_model_selected_without_persona_keeps_streamer_none():
    web_ui = _create_web_ui()
    web_ui.cfg.override = Mock()
    web_ui.bot = None

    update = web_ui._on_model_selected("neu:1")

    web_ui.cfg.override.assert_called_once_with("core", {"model_name": "neu:1"})
    web_ui.factory.get_streamer_for_persona.assert_not_called()
    assert web_ui.streamer is None
    assert update["visible"] is True


def test_on_model_selected_empty_choice_is_noop():
    web_ui = _create_web_ui()
    web_ui.cfg.override = Mock()

    update = web_ui._on_model_selected("")

    web_ui.cfg.override.assert_not_called()
    assert update["visible"] is False


def test_persona_selected_updates_reads_current_model_from_cfg():
    """Das Greeting muss das aktuell wirksame Modell zeigen, nicht das vom Start."""

    web_ui = _create_web_ui()
    web_ui.cfg.core = {"model_name": "override:1"}
    web_ui.cfg.ensemble = "test"
    persona = {"name": "Karl", "description": "Testpersona"}

    updates = web_ui._persona_selected_updates(
        "karl", persona, "Hallo {persona_name} — {model_name}", "Tippe hier"
    )

    assert len(updates) == len(PERSONA_OUTPUT_KEYS)
    greeting_update = updates[5]
    assert "override:1" in greeting_update["value"]


# ---- Spracheingabe (STT MVP, #13) -------------------------------------------


def test_stt_unavailable_by_default_config():
    """SimpleNamespace-Config ohne stt-Sektion → Mikro aus, kein Crash."""

    web_ui = _create_web_ui()

    assert web_ui.stt_available is False
    assert web_ui.stt_cfg == {}


def test_on_mic_recorded_without_audio_is_noop():
    web_ui = _create_web_ui()

    input_update, mic_update = web_ui._on_mic_recorded(None, "bestehender Text")

    assert "value" not in input_update
    assert "value" not in mic_update


def test_on_mic_recorded_appends_transcript_and_clears_mic():
    web_ui = _create_web_ui()

    with patch("ui.web_ui.transcribe_wav", return_value="Hallo Welt"):
        input_update, mic_update = web_ui._on_mic_recorded("/tmp/x.wav", "Schon da")

    assert input_update["value"] == "Schon da Hallo Welt"
    assert mic_update["value"] is None


def test_on_mic_recorded_error_warns_and_keeps_text():
    web_ui = _create_web_ui()

    with (
        patch("ui.web_ui.transcribe_wav", side_effect=RuntimeError("kaputt")),
        patch("ui.web_ui.gr.Warning") as mock_warning,
    ):
        input_update, mic_update = web_ui._on_mic_recorded("/tmp/x.wav", "Schon da")

    mock_warning.assert_called_once()
    assert "value" not in input_update
    assert mic_update["value"] is None


def test_on_mic_recorded_empty_transcript_is_noop_but_clears_mic():
    web_ui = _create_web_ui()

    with patch("ui.web_ui.transcribe_wav", return_value=""):
        input_update, mic_update = web_ui._on_mic_recorded("/tmp/x.wav", "Schon da")

    assert "value" not in input_update
    assert mic_update["value"] is None


def test_persona_selected_updates_shows_mic_only_when_stt_available():
    persona = {"name": "Karl", "description": "Testpersona"}

    for available, expected in ((True, True), (False, False)):
        web_ui = _create_web_ui()
        web_ui.cfg.core = {"model_name": "m:1"}
        web_ui.cfg.ensemble = "test"
        web_ui.stt_available = available

        updates = web_ui._persona_selected_updates(
            "karl", persona, "Hallo {persona_name} — {model_name}", "Tippe hier"
        )

        assert updates[28]["visible"] is expected


def test_reset_updates_hides_mic():
    web_ui = _create_web_ui()
    web_ui.stt_available = True

    updates = web_ui._reset_ui_updates()

    assert updates[28]["visible"] is False
    assert updates[28]["value"] is None


# ---- Briefing (RSS MVP, #15) ------------------------------------------------


def _briefing_web_ui():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    web_ui.briefing_enabled = True
    web_ui.briefing_cfg = {
        "enabled": True,
        "timeout_connect": 1.0,
        "timeout_read": 1.0,
        "feeds": [{"name": "quelle", "url": "https://example.org/rss"}],
    }
    streamer = Mock()
    streamer.persona_options = {}
    streamer.stream.return_value = iter(["Ant", "wort"])
    web_ui.streamer = streamer
    return web_ui


def test_briefing_disabled_by_default_config():
    web_ui = _create_web_ui()

    assert web_ui.briefing_enabled is False

    outputs = list(web_ui.respond_briefing([], []))
    assert len(outputs) == 1
    web_ui.factory.get_streamer_for_persona.assert_not_called()


def test_respond_briefing_streams_summary_with_injected_context():
    web_ui = _briefing_web_ui()
    history_state = [{"role": "user", "content": "früher"}]

    with (
        patch(
            "ui.web_ui.fetch_briefing_items",
            return_value=(["📰 hint"], [("quelle: Titel", "Text")]),
        ) as mock_fetch,
        patch("ui.web_ui.inject_briefing_context") as mock_inject,
        patch("ui.web_ui.context_near_limit", return_value=False),
    ):
        outputs = list(web_ui.respond_briefing([], history_state))

    mock_fetch.assert_called_once()
    assert mock_fetch.call_args[0][2] == (1.0, 1.0)  # Timeout-Tuple aus der Config
    mock_inject.assert_called_once()
    injected_history, injected_items = mock_inject.call_args[0]
    assert injected_items == [("quelle: Titel", "Text")]

    final_chat, final_state = outputs[-1][1], outputs[-1][2]
    # User-Bubble (Prompt), Hint-Bubble, gestreamte Antwort
    assert final_chat[0] == ("briefing_user_prompt", None)
    assert final_chat[1] == (None, "📰 hint")
    assert final_chat[-1] == (None, "Antwort")
    assert final_state[-2] == {"role": "user", "content": "briefing_user_prompt"}
    assert final_state[-1] == {"role": "assistant", "content": "Antwort"}
    # Copy-Disziplin: das übergebene gr.State-Objekt bleibt unangetastet
    assert history_state == [{"role": "user", "content": "früher"}]


def test_respond_briefing_without_items_shows_empty_note_and_skips_stream():
    web_ui = _briefing_web_ui()

    with patch("ui.web_ui.fetch_briefing_items", return_value=(["📰 down"], [])):
        outputs = list(web_ui.respond_briefing([], []))

    final_chat = outputs[-1][1]
    assert final_chat[-1] == (None, "briefing_empty")
    web_ui.streamer.stream.assert_not_called()


def test_persona_selected_updates_toggles_briefing_button():
    persona = {"name": "Karl", "description": "Testpersona"}

    for enabled in (True, False):
        web_ui = _create_web_ui()
        web_ui.cfg.core = {"model_name": "m:1"}
        web_ui.cfg.ensemble = "test"
        web_ui.briefing_enabled = enabled

        updates = web_ui._persona_selected_updates(
            "karl", persona, "Hallo {persona_name} — {model_name}", "Tippe hier"
        )

        assert updates[29]["visible"] is enabled


def test_reset_updates_hides_briefing_button():
    web_ui = _create_web_ui()
    web_ui.briefing_enabled = True

    updates = web_ui._reset_ui_updates()

    assert updates[29]["visible"] is False


# ---- Vorlesen (TTS im WebUI, #25) --------------------------------------------


def _install_fake_piper(monkeypatch):
    piper_module = types.ModuleType("piper")
    voice_module = types.ModuleType("piper.voice")

    class _Voice:
        @staticmethod
        def load(path):
            return object()

    voice_module.PiperVoice = _Voice
    monkeypatch.setitem(sys.modules, "piper", piper_module)
    monkeypatch.setitem(sys.modules, "piper.voice", voice_module)


def test_tts_web_disabled_by_default_config():
    """SimpleNamespace-Config ohne tts-Sektion → Button aus, kein Crash."""

    web_ui = _create_web_ui()

    assert web_ui.tts_web_enabled is False


def test_on_read_aloud_without_reply_warns_and_stays_hidden():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"

    with patch("ui.web_ui.gr.Warning") as mock_warning:
        update = web_ui._on_read_aloud([{"role": "user", "content": "Hallo"}])

    mock_warning.assert_called_once()
    assert update["visible"] is False


def test_on_read_aloud_synthesizes_last_assistant_reply(monkeypatch):
    _install_fake_piper(monkeypatch)
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    web_ui.tts_cfg = {"voices": {"default": {"de": "stimme"}}}
    history = [
        {"role": "assistant", "content": "Alte Antwort"},
        {"role": "user", "content": "Frage"},
        {"role": "assistant", "content": "Neueste Antwort"},
    ]

    with patch("tts.piper_tts.create_wav") as mock_create:
        update = web_ui._on_read_aloud(history)

    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args[0] == "Neueste Antwort"
    assert args[1] == "Karl"
    assert kwargs["tts_cfg"] == web_ui.tts_cfg
    assert update["visible"] is True
    assert update["value"].endswith(".wav")


def test_on_read_aloud_error_warns_and_stays_hidden(monkeypatch):
    _install_fake_piper(monkeypatch)
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"

    with (
        patch(
            "tts.piper_tts.create_wav",
            side_effect=FileNotFoundError("voices/stimme.onnx"),
        ),
        patch("ui.web_ui.gr.Warning") as mock_warning,
    ):
        update = web_ui._on_read_aloud([{"role": "assistant", "content": "Hi"}])

    mock_warning.assert_called_once()
    assert update["visible"] is False


def test_persona_selected_updates_toggles_read_aloud_button():
    persona = {"name": "Karl", "description": "Testpersona"}

    for enabled in (True, False):
        web_ui = _create_web_ui()
        web_ui.cfg.core = {"model_name": "m:1"}
        web_ui.cfg.ensemble = "test"
        web_ui.tts_web_enabled = enabled

        updates = web_ui._persona_selected_updates(
            "karl", persona, "Hallo {persona_name} — {model_name}", "Tippe hier"
        )

        assert updates[30]["visible"] is enabled


def test_reset_updates_hides_read_aloud_button_and_player():
    web_ui = _create_web_ui()
    web_ui.tts_web_enabled = True

    updates = web_ui._reset_ui_updates()

    assert updates[30]["visible"] is False
    assert updates[31]["visible"] is False
    assert updates[31]["value"] is None


# --- Feedback votes (#40) ---------------------------------------------------


def _fake_like(index=(2, 1), value="Antwort!", liked=True):
    return SimpleNamespace(index=index, value=value, liked=liked)


def _read_votes(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_chat_like_appends_upvote_jsonl(tmp_path):
    """The backwards walk skips UI-only rows (wiki hint) to find the question."""

    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path / "votes.jsonl")
    history = [("Hallo?", None), (None, "wiki hint"), (None, "Antwort!")]
    meta = {"persona": "DORIS", "model": "m1", "app": "web"}

    web_ui._on_chat_like(history, meta, _fake_like(index=(2, 1), liked=True))

    votes = _read_votes(web_ui.feedback_log_path)
    assert len(votes) == 1
    vote = votes[0]
    assert vote["vote"] == "up"
    assert vote["question"] == "Hallo?"
    assert vote["answer"] == "Antwort!"
    assert vote["persona"] == "DORIS"
    assert vote["model"] == "m1"
    assert vote["index"] == [2, 1]
    assert vote["ts"]


def test_chat_like_downvote_on_paired_history(tmp_path):
    """Loaded conversations pair (question, answer) in a single row."""

    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path / "votes.jsonl")
    history = [("Frage", "Antwort")]

    web_ui._on_chat_like(
        history, {}, _fake_like(index=(0, 1), value="Antwort", liked=False)
    )

    vote = _read_votes(web_ui.feedback_log_path)[0]
    assert vote["vote"] == "down"
    assert vote["question"] == "Frage"
    assert vote["answer"] == "Antwort"


def test_chat_like_selftalk_uses_start_prompt_and_meta_persona(tmp_path):
    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path / "votes.jsonl")
    history = [("Prompt", None), (None, "LEAH: Hi"), (None, "DORIS: Na?")]
    meta = {"persona": "self-talk:LEAH,DORIS", "model": "m1", "app": "web"}

    web_ui._on_chat_like(history, meta, _fake_like(index=(2, 1), value="DORIS: Na?"))

    vote = _read_votes(web_ui.feedback_log_path)[0]
    assert vote["question"] == "Prompt"
    assert vote["persona"] == "self-talk:LEAH,DORIS"
    assert vote["answer"] == "DORIS: Na?"


def test_chat_like_two_votes_append_two_lines(tmp_path):
    """Append-only event log: a revote adds a line, consumers dedup by index."""

    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path / "votes.jsonl")
    history = [("Frage", None), (None, "Antwort")]

    web_ui._on_chat_like(history, {}, _fake_like(index=(1, 1), liked=True))
    web_ui._on_chat_like(history, {}, _fake_like(index=(1, 1), liked=False))

    votes = _read_votes(web_ui.feedback_log_path)
    assert [v["vote"] for v in votes] == ["up", "down"]


def test_chat_like_never_raises_on_write_error(tmp_path, caplog):
    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path)  # a directory → OSError on open

    with caplog.at_level(logging.ERROR):
        web_ui._on_chat_like([("F", None), (None, "A")], {}, _fake_like(index=(1, 1)))

    assert "Could not write feedback log" in caplog.text


def test_chat_like_handles_garbage_input(tmp_path):
    """Empty history, missing meta and a broken index still produce a vote line."""

    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path / "votes.jsonl")

    web_ui._on_chat_like(None, None, _fake_like(index=None, value="Antwort"))

    vote = _read_votes(web_ui.feedback_log_path)[0]
    assert vote["question"] == ""
    assert vote["persona"] == ""
    assert vote["answer"] == "Antwort"
    assert vote["index"] == [-1, 1]


def test_find_question_returns_empty_on_garbage():
    assert WebUI._find_question_for_row([], 0) == ""
    assert WebUI._find_question_for_row(None, 3) == ""
    assert WebUI._find_question_for_row([(None, "nur Bot")], 5) == ""


def test_chat_like_ignores_votes_on_user_messages(tmp_path):
    """Gradio also shows thumbs on the user row — those votes carry no signal."""

    web_ui = _create_web_ui()
    web_ui.feedback_log_path = str(tmp_path / "votes.jsonl")
    history = [("Frage", None), (None, "Antwort")]

    web_ui._on_chat_like(history, {}, _fake_like(index=(0, 0), value="Frage"))

    assert not (tmp_path / "votes.jsonl").exists()


# ---- Stream-Steuerung: Stop + Regenerate (#35) -------------------------------


class _BlockingStream:
    """Token source that never ends on its own — only a stop can end it.

    Records whether close() ran, which is what actually terminates the LLM
    stream in the provider's finally block.
    """

    def __init__(self, token="tok "):
        self.token = token
        self.closed = False
        self.emitted = 0

    def __iter__(self):
        return self

    def __next__(self):
        self.emitted += 1
        return self.token

    def close(self):
        self.closed = True


def test_stop_button_ends_the_stream_and_keeps_the_partial_answer():
    web_ui = _create_web_ui()
    stream = _BlockingStream("Teil ")
    streamer = Mock()
    streamer.stream.return_value = stream
    web_ui.streamer = streamer

    outputs = []
    generator = web_ui._stream_reply([], [])
    # Uhr läuft in 1-s-Schritten, damit jeder Token die 0.1-s-Drossel passiert.
    clock = iter(1000.0 + i for i in range(100))
    with patch("ui.web_ui.time.monotonic", side_effect=lambda: next(clock)):
        outputs.append(next(generator))
        # Stoppen wie der Button es tut, während der Stream noch läuft.
        web_ui._on_stop_stream()
        outputs.extend(generator)

    final_chat = outputs[-1][1]
    reply = final_chat[-1][1]
    assert reply.startswith("Teil ")
    assert "web_stream_stopped_suffix" in reply  # Locale-Key via Test-Stub
    assert stream.closed, "der Token-Stream muss beim Stop geschlossen werden"


def test_stop_clears_the_switch_so_the_next_stream_runs():
    web_ui = _create_web_ui()
    web_ui._on_stop_stream()  # Stop ohne laufenden Stream: darf nichts kaputt machen

    streamer = Mock()
    streamer.stream.return_value = iter(["Hallo ", "Welt"])
    web_ui.streamer = streamer
    with patch("ui.web_ui.time.monotonic", return_value=1000.0):
        outputs = list(web_ui._stream_reply([], []))

    assert outputs[-1][1][-1] == (None, "Hallo Welt")
    assert web_ui._stream_stop is None


def test_stale_generator_ignores_a_newer_streams_stop_switch():
    """Ein alter Generator darf nicht auf den Kill-Switch des neuen reagieren."""
    web_ui = _create_web_ui()
    old_stop = web_ui._arm_stream_stop()
    new_stop = web_ui._arm_stream_stop()

    old_stop.set()
    assert web_ui._stop_requested(old_stop) is False
    new_stop.set()
    assert web_ui._stop_requested(new_stop) is True


def test_streaming_button_updates_swap_send_and_stop():
    web_ui = _create_web_ui()

    send, stop, regenerate = web_ui._streaming_button_updates(streaming=True)
    assert send["visible"] is False
    assert stop["visible"] is True
    assert regenerate["interactive"] is False

    send, stop, regenerate = web_ui._streaming_button_updates(streaming=False)
    assert send["visible"] is True
    assert stop["visible"] is False
    assert regenerate["interactive"] is True


def test_stream_controls_flip_buttons_on_the_first_yield():
    """Kein vorgeschaltetes Event: der erste Yield trägt die Button-Updates.

    Ein eigenes `.then()`-Event davor kostete gemessen ~3,5 s bis zum ersten
    Token (Queue-Roundtrip) und hätte #17 zunichte gemacht.
    """
    web_ui = _create_web_ui()

    def _fake_stream():
        yield ("", [("Frage", None)], [])
        yield (None, [("Frage", None), (None, "Teil")], [])

    outputs = list(web_ui._with_stream_controls(_fake_stream()))

    # Erster Yield: Stop sichtbar, Send weg — ohne zusätzliche Runde.
    assert outputs[0][4]["visible"] is True
    assert outputs[0][3]["visible"] is False
    # Zwischendurch bleiben die Buttons unverändert.
    assert outputs[1][3] == gr.update()
    # Letzter Yield: zurück in den Ruhezustand.
    assert outputs[-1][3]["visible"] is True
    assert outputs[-1][4]["visible"] is False


def test_stream_controls_repeat_real_values_in_the_final_yield():
    """Der Schluss-Yield darf für gr.State keinen Update-Marker schicken."""
    web_ui = _create_web_ui()
    final_state = [{"role": "assistant", "content": "fertig"}]

    def _fake_stream():
        yield (None, [("Frage", None), (None, "fertig")], final_state)

    outputs = list(web_ui._with_stream_controls(_fake_stream()))

    assert outputs[-1][1] == [("Frage", None), (None, "fertig")]
    assert outputs[-1][2] is final_state


def test_stream_controls_pass_through_an_empty_stream():
    web_ui = _create_web_ui()

    assert list(web_ui._with_stream_controls(iter(()))) == []


def test_regenerate_drops_last_answer_and_streams_again():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    # Snapshot beim Aufruf: _stream_reply hängt die neue Antwort an dieselbe
    # Liste an, hinterher wäre nicht mehr sichtbar, was gesendet wurde.
    sent_snapshot = []

    def _stream(*_args, **kwargs):
        sent_snapshot.extend(dict(m) for m in kwargs["messages"])
        return iter(["Neue ", "Antwort"])

    streamer.stream.side_effect = _stream
    web_ui.streamer = streamer

    chat_history = [("Frage", None), (None, "Alte Antwort")]
    history_state = [
        {"role": "user", "content": "Frage"},
        {"role": "assistant", "content": "Alte Antwort"},
    ]

    with patch("ui.web_ui.time.monotonic", return_value=1000.0):
        outputs = list(web_ui._on_regenerate(chat_history, history_state))

    final_chat, final_state = outputs[-1][1], outputs[-1][2]
    assert final_chat[-1] == (None, "Neue Antwort")
    assert "Alte Antwort" not in [row[1] for row in final_chat]
    # Die Frage bleibt im LLM-Kontext, nur die Antwort wurde ersetzt.
    assert final_state[0] == {"role": "user", "content": "Frage"}
    assert final_state[-1] == {"role": "assistant", "content": "Neue Antwort"}
    assert len(final_state) == 2
    # Der gleiche Kontext geht erneut ans Modell — kein veränderter Prompt und
    # ohne die verworfene Antwort.
    assert sent_snapshot == [{"role": "user", "content": "Frage"}]


def test_regenerate_keeps_wiki_hint_rows():
    """Wiki-Hints sind Bot-Zeilen, stehen aber vor der Antwort und bleiben."""
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.stream.return_value = iter(["Neu"])
    web_ui.streamer = streamer

    chat_history = [("Frage", None), (None, "🕵️ Hinweis"), (None, "Alte Antwort")]
    history_state = [
        {"role": "user", "content": "Frage"},
        {"role": "assistant", "content": "Alte Antwort"},
    ]

    with patch("ui.web_ui.time.monotonic", return_value=1000.0):
        outputs = list(web_ui._on_regenerate(chat_history, history_state))

    rows = [row[1] for row in outputs[-1][1]]
    assert "🕵️ Hinweis" in rows
    assert "Alte Antwort" not in rows


def test_regenerate_without_an_answer_warns_and_changes_nothing():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    web_ui.streamer = Mock()

    chat_history = [("Frage", None)]
    history_state = [{"role": "user", "content": "Frage"}]

    with patch("ui.web_ui.gr.Warning") as warning:
        outputs = list(web_ui._on_regenerate(chat_history, history_state))

    warning.assert_called_once()
    web_ui.streamer.stream.assert_not_called()
    assert outputs[-1][1] == chat_history
    assert outputs[-1][2] == history_state


def test_regenerate_without_persona_is_a_no_op():
    web_ui = _create_web_ui()
    web_ui.bot = None

    outputs = list(web_ui._on_regenerate([], []))

    assert len(outputs) == 1


def test_reset_sets_the_stream_kill_switch():
    """cancels allein reicht nicht — der Reset muss die Backend-Arbeit stoppen."""
    web_ui = _create_web_ui()
    stop = web_ui._arm_stream_stop()

    web_ui._on_reset_to_start()

    assert stop.is_set()


def test_reset_updates_hide_stop_and_regenerate():
    web_ui = _create_web_ui()

    updates = web_ui._reset_ui_updates()
    stop_index = PERSONA_OUTPUT_KEYS.index("stop_btn")
    regenerate_index = PERSONA_OUTPUT_KEYS.index("regenerate_btn")

    assert updates[stop_index]["visible"] is False
    assert updates[regenerate_index]["visible"] is False


def test_persona_selection_shows_regenerate_but_not_stop():
    web_ui = _create_web_ui()
    web_ui.cfg.core = {"model_name": "m"}
    web_ui.cfg.ensemble = "test"

    updates = web_ui._persona_selected_updates(
        "karl", {"name": "Karl", "description": "d"}, "Hallo {persona_name}", "Tippe"
    )
    stop_index = PERSONA_OUTPUT_KEYS.index("stop_btn")
    regenerate_index = PERSONA_OUTPUT_KEYS.index("regenerate_btn")

    assert updates[stop_index]["visible"] is False
    assert updates[regenerate_index]["visible"] is True


def test_self_talk_stream_stops_between_turns():
    web_ui = _create_web_ui()
    runner = Mock()
    turns = [("A", "erste", False, None), ("B", "zweite", False, None)]
    runner.run_turn.side_effect = turns
    web_ui.self_talk_runner = runner

    generator = web_ui._run_self_talk_stream([], [])
    with patch("ui.web_ui.time.monotonic", return_value=1000.0):
        next(generator)  # erster Turn läuft
        web_ui._on_stop_stream()
        list(generator)

    # Der laufende Turn wird fertig, ein weiterer startet nicht mehr.
    assert runner.run_turn.call_count == 1


# ---- Wiki-Quellen (#32) -----------------------------------------------------
# Der Punkt der Anzeige ist nicht "es gab eine Quelle", sondern *welcher Text*
# im Prompt gelandet ist und ob er an wiki.snippet_limit abgeschnitten wurde.


def _web_ui_with_texts():
    web_ui = _create_web_ui()
    catalog = Texts("de")
    web_ui.texts = catalog
    web_ui._t = catalog.format
    return web_ui


def test_format_wiki_sources_shows_link_length_and_the_injected_text():
    web_ui = _web_ui_with_texts()

    markdown = web_ui._format_wiki_sources(
        [
            WikiSnippet(
                topic="Deutschland",
                snippet="Deutschland ist ein Bundesstaat.",
                link="http://127.0.0.1:8080/wiki/Deutschland",
                source="local",
                full_length=8432,
            )
        ]
    )

    assert "[Deutschland](http://127.0.0.1:8080/wiki/Deutschland)" in markdown
    assert "Offline-Archiv" in markdown
    # Gekürzt: beide Zahlen müssen dastehen, sonst ist nicht erkennbar, wie viel
    # des Artikels das Modell nie gesehen hat.
    assert "32 von 8432 Zeichen" in markdown
    assert "gekürzt" in markdown
    assert "> Deutschland ist ein Bundesstaat." in markdown


def test_format_wiki_sources_marks_complete_snippets_as_complete():
    web_ui = _web_ui_with_texts()

    markdown = web_ui._format_wiki_sources(
        [WikiSnippet(topic="Kiwix", snippet="Kurz.", source="online", full_length=5)]
    )

    assert "vollständig" in markdown
    assert "gekürzt" not in markdown
    assert "Wikipedia (online)" in markdown


def test_format_wiki_sources_numbers_every_snippet():
    web_ui = _web_ui_with_texts()

    markdown = web_ui._format_wiki_sources(
        [
            WikiSnippet(topic="Eins", snippet="A", full_length=1),
            WikiSnippet(topic="Zwei", snippet="B", full_length=1),
        ]
    )

    assert "### 1. Eins" in markdown
    assert "### 2. Zwei" in markdown
    assert markdown.count("---") == 1


def test_format_wiki_sources_is_empty_without_snippets():
    assert _web_ui_with_texts()._format_wiki_sources([]) == ""


def test_wiki_source_updates_hide_the_accordion_without_hits():
    accordion, markdown = _web_ui_with_texts()._wiki_source_updates([])

    assert accordion["visible"] is False
    assert markdown["value"] == ""


def test_respond_streaming_publishes_the_sources_before_the_first_token():
    """Die Quellen müssen in denselben Yields mitreisen (kein .then()-Umweg)."""
    web_ui = _web_ui_with_texts()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {}
    streamer.stream.return_value = iter(["Hi"])
    web_ui.streamer = streamer

    snippet = WikiSnippet(
        topic="Deutschland",
        snippet="Berlin ist die Hauptstadt.",
        link="http://localhost:8080/Deutschland",
        source="local",
        full_length=9000,
    )

    md_index = STREAM_OUTPUT_KEYS.index("sources_md")
    accordion_index = STREAM_OUTPUT_KEYS.index("sources_accordion")

    # Die Chat-Liste wird in-place mutiert — für die Reihenfolge muss deshalb
    # pro Yield ein Abzug genommen werden, nicht am Ende die Liste gelesen.
    snapshots = []
    with (
        patch(
            "ui.web_ui.lookup_wiki_snippet",
            return_value=(["🕵️ Hinweis"], [snippet]),
        ),
        patch("ui.web_ui.inject_wiki_context"),
        patch("ui.web_ui.context_near_limit", return_value=False),
    ):
        for item in web_ui.respond_streaming("Frage", [], []):
            snapshots.append((item[md_index], item[accordion_index], list(item[1])))

    published = [
        md["value"]
        for md, _, _ in snapshots
        if isinstance(md, dict) and md.get("value")
    ]
    assert published, "Der injizierte Snippet-Text wurde nie an die UI geschickt"
    assert "Berlin ist die Hauptstadt." in published[0]
    assert any(
        isinstance(acc, dict) and acc.get("visible") is True for _, acc, _ in snapshots
    )

    # Der Token-Stream startet erst danach — die Quellen stehen also, bevor die
    # erste Antwort sichtbar wird.
    first_source_yield = next(
        i
        for i, (md, _, _) in enumerate(snapshots)
        if isinstance(md, dict) and md.get("value")
    )
    first_token_yield = next(
        i
        for i, (_, _, chat) in enumerate(snapshots)
        if chat and chat[-1] == (None, "Hi")
    )
    assert first_source_yield < first_token_yield


def test_respond_streaming_clears_stale_sources_on_a_new_question():
    web_ui = _web_ui_with_texts()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {}
    streamer.stream.return_value = iter(["Hi"])
    web_ui.streamer = streamer

    with (
        patch("ui.web_ui.lookup_wiki_snippet", return_value=([], [])),
        patch("ui.web_ui.context_near_limit", return_value=False),
    ):
        outputs = list(web_ui.respond_streaming("Frage", [], []))

    accordion_index = STREAM_OUTPUT_KEYS.index("sources_accordion")
    assert outputs[0][accordion_index]["visible"] is False


def test_reset_updates_hide_the_sources_accordion():
    updates = _create_web_ui()._reset_ui_updates()

    assert updates[PERSONA_OUTPUT_KEYS.index("sources_accordion")]["visible"] is False
    assert updates[PERSONA_OUTPUT_KEYS.index("sources_md")]["value"] == ""
