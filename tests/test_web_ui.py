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

    with patch("ui.web_ui.lookup_wiki_snippet", return_value=(None, None, None)), \
         patch("ui.web_ui.inject_wiki_context"), \
         patch("ui.web_ui.utils.context_near_limit", return_value=True), \
         patch("ui.web_ui.get_drink", return_value="☕"), \
         patch(
             "ui.web_ui.utils.karl_prepare_quick_and_dirty",
             side_effect=lambda history, limit: history,
         ) as mock_prepare:
        list(web_ui.respond_streaming("Hallo", chat_history))

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

    with patch("ui.web_ui.lookup_wiki_snippet", return_value=(None, None, None)), \
         patch("ui.web_ui.inject_wiki_context"), \
         patch("ui.web_ui.utils.context_near_limit", return_value=True), \
         patch("ui.web_ui.get_drink", return_value="☕"), \
         patch("ui.web_ui.utils.karl_prepare_quick_and_dirty") as mock_prepare:
        list(web_ui.respond_streaming("Hallo", chat_history))

    mock_prepare.assert_not_called()
    assert "Überspringe 'karl_prepare_quick_and_dirty'" in caplog.text
    streamer.stream.assert_called_once()
