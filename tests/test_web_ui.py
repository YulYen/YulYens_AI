"""Tests for the WebUI-specific server configuration."""

import logging
import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from ui.web_ui import WebUI


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
    assert all(len(item) == 3 for item in outputs)
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
            return_value=(["🕵️ Hinweis"], [("Thema", "Snippet")]),
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

    assert len(updates) == 32
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

    assert len(updates) == 32
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
