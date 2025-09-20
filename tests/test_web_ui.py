"""Tests für die WebUI-spezifische Server-Konfiguration."""

import logging
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ui.web_ui import WebUI


def test_webui_start_server_uses_configured_host_and_port():
    """`demo.launch` muss mit den konfigurierten Host/Port-Werten aufgerufen werden."""

    dummy_config = SimpleNamespace()

    web_ui = WebUI(
        factory=Mock(),
        config=dummy_config,
        keyword_finder=Mock(),
        ip="127.0.0.1",
        wiki_snippet_limit=42,
        wiki_mode="offline",
        proxy_base="http://proxy",
        web_host="0.0.0.0",
        web_port="9000",
        wiki_timeout=1.0,
    )

    demo = Mock()

    web_ui._start_server(demo)

    demo.launch.assert_called_once_with(
        server_name="0.0.0.0", server_port=9000, show_api=False
    )


def _create_web_ui():
    dummy_config = SimpleNamespace()
    return WebUI(
        factory=Mock(),
        config=dummy_config,
        keyword_finder=None,
        ip="127.0.0.1",
        wiki_snippet_limit=42,
        wiki_mode="offline",
        proxy_base="http://proxy",
        web_host="0.0.0.0",
        web_port="9000",
        wiki_timeout=1.0,
    )


def test_respond_streaming_prepares_history_with_valid_num_ctx():
    web_ui = _create_web_ui()
    web_ui.bot = "Karl"
    streamer = Mock()
    streamer.persona_options = {"num_ctx": "4096"}
    streamer.stream.return_value = iter(["Hallo"])
    web_ui.streamer = streamer

    chat_history = []
    history_state = []

    with patch("ui.web_ui.lookup_wiki_snippet", return_value=(None, None, None)), \
         patch("ui.web_ui.inject_wiki_context"), \
         patch("ui.web_ui.utils.context_near_limit", return_value=True), \
         patch("ui.web_ui.get_drink", return_value="☕"), \
         patch(
             "ui.web_ui.utils.karl_prepare_quick_and_dirty",
             side_effect=lambda history, limit: history,
         ) as mock_prepare:
        list(web_ui.respond_streaming("Hallo", chat_history, history_state))

    mock_prepare.assert_called_once()
    assert mock_prepare.call_args[0][1] == 4096
    streamer.stream.assert_called_once()


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

    with patch("ui.web_ui.lookup_wiki_snippet", return_value=(None, None, None)), \
         patch("ui.web_ui.inject_wiki_context"), \
         patch("ui.web_ui.utils.context_near_limit", return_value=True), \
         patch("ui.web_ui.get_drink", return_value="☕"), \
         patch("ui.web_ui.utils.karl_prepare_quick_and_dirty") as mock_prepare:
        list(web_ui.respond_streaming("Hallo", chat_history, history_state))

    mock_prepare.assert_not_called()
    assert "Überspringe 'karl_prepare_quick_and_dirty'" in caplog.text
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

    with patch("ui.web_ui.lookup_wiki_snippet", return_value=(None, None, None)), \
         patch("ui.web_ui.utils.context_near_limit", return_value=False):
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
