"""kiwix-serve wird nur dort gestartet, wo die Config es hinstellt (#83)."""

from types import SimpleNamespace

import pytest
from wiki import kiwix_autostart


def _cfg(host):
    return SimpleNamespace(
        wiki={
            "mode": "offline",
            "offline": {
                "autostart": True,
                "host": host,
                "kiwix_port": 8080,
                "kiwix_exe": "kiwix-serve",
                "zim_path": "wiki.zim",
                "startup_timeout_s": 0,
            },
        }
    )


@pytest.fixture
def started(monkeypatch):
    """Fängt den Start ab; Kiwix gilt als nicht erreichbar."""
    calls = []
    monkeypatch.setattr(kiwix_autostart.subprocess, "Popen", calls.append)

    def _down(*_args, **_kwargs):
        raise OSError("nicht da")

    monkeypatch.setattr(kiwix_autostart.requests, "get", _down)
    return calls


def test_kiwix_is_bound_to_the_configured_address(started):
    """Ohne `--address` lauscht kiwix-serve auf allen Schnittstellen.

    Gesehen am 2026-11-06: der Server meldete sich unter der LAN-Adresse, die
    Offline-Wikipedia war für jeden im WLAN lesbar — obwohl
    `wiki.offline.host` auf `127.0.0.1` steht.
    """
    kiwix_autostart.ensure_kiwix_running_if_offlinemode_and_autostart(_cfg("127.0.0.1"))

    assert started == [
        ["kiwix-serve", "--port=8080", "--address=127.0.0.1", "wiki.zim"]
    ]


def test_a_host_name_is_not_passed_as_an_address(started):
    """`--address` nimmt eine IP. Ein Name wie `localhost` bliebe ein Startfehler."""
    kiwix_autostart.ensure_kiwix_running_if_offlinemode_and_autostart(_cfg("localhost"))

    assert started == [["kiwix-serve", "--port=8080", "wiki.zim"]]
