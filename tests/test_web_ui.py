"""Tests für die WebUI-spezifische Server-Konfiguration."""

from types import SimpleNamespace
from unittest.mock import Mock

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
