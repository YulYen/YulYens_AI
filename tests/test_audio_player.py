"""Cross-platform audio dispatch (#34).

No audio hardware involved: the platform and the availability of the player
binaries are injected, so the dispatch logic is testable on any machine — which
is the whole point, since the project runs Windows-first while CI runs Linux.
"""

from pathlib import Path

import pytest
from tts import audio_player
from tts.audio_player import find_player, play_wav

WAV = Path("out") / "test.wav"


@pytest.fixture
def which(monkeypatch):
    """Control which player binaries 'exist'."""
    available: dict[str, str] = {}

    def _which(name):
        return available.get(name)

    monkeypatch.setattr(audio_player.shutil, "which", _which)
    return available


@pytest.fixture
def spawned(monkeypatch):
    calls = {"popen": [], "run": []}
    monkeypatch.setattr(
        audio_player.subprocess,
        "Popen",
        lambda cmd, **kw: calls["popen"].append((cmd, kw)),
    )
    monkeypatch.setattr(
        audio_player.subprocess,
        "run",
        lambda cmd, **kw: calls["run"].append((cmd, kw)),
    )
    return calls


# ---- Player selection ----------------------------------------------------


def test_linux_prefers_paplay(which):
    which.update({"paplay": "/usr/bin/paplay", "aplay": "/usr/bin/aplay"})

    assert find_player("linux") == ("/usr/bin/paplay", ())


def test_linux_falls_back_to_aplay_then_ffplay(which):
    which["aplay"] = "/usr/bin/aplay"
    assert find_player("linux") == ("/usr/bin/aplay", ("-q",))

    which.clear()
    which["ffplay"] = "/usr/bin/ffplay"
    binary, args = find_player("linux")
    assert binary == "/usr/bin/ffplay"
    assert "-nodisp" in args and "-autoexit" in args


def test_macos_uses_afplay(which):
    which["afplay"] = "/usr/bin/afplay"

    assert find_player("darwin") == ("/usr/bin/afplay", ())


def test_macos_does_not_pick_a_linux_player(which):
    which["aplay"] = "/usr/bin/aplay"

    assert find_player("darwin") is None


def test_no_player_available_returns_none(which):
    assert find_player("linux") is None


def test_unknown_platform_has_no_candidates(which):
    which.update({"paplay": "/usr/bin/paplay", "afplay": "/usr/bin/afplay"})

    assert find_player("freebsd13") is None


# ---- Playback ------------------------------------------------------------


def test_non_blocking_playback_spawns_without_waiting(which, spawned):
    which["paplay"] = "/usr/bin/paplay"

    assert play_wav(WAV, block=False, platform="linux") is True
    command, kwargs = spawned["popen"][0]
    assert command == ["/usr/bin/paplay", str(WAV)]
    # Der Terminal-Chat darf nicht blockieren und die Konsole nicht zugemüllt werden.
    assert kwargs["stdout"] == audio_player.subprocess.DEVNULL
    assert kwargs["stderr"] == audio_player.subprocess.DEVNULL
    assert spawned["run"] == []


def test_blocking_playback_waits(which, spawned):
    which["aplay"] = "/usr/bin/aplay"

    assert play_wav(WAV, block=True, platform="linux") is True
    command, kwargs = spawned["run"][0]
    assert command == ["/usr/bin/aplay", "-q", str(WAV)]
    assert kwargs["check"] is False
    assert spawned["popen"] == []


def test_missing_player_is_silent_and_reports_false(which, spawned, caplog):
    """Headless ohne Audio-Tooling ist kein Fehler, nur nichts zu tun."""
    import logging

    caplog.set_level(logging.INFO)

    assert play_wav(WAV, platform="linux") is False
    assert spawned["popen"] == [] and spawned["run"] == []
    assert "No audio player found" in caplog.text


def test_player_that_cannot_be_started_is_swallowed(which, monkeypatch, caplog):
    which["paplay"] = "/usr/bin/paplay"

    def _boom(*_args, **_kwargs):
        raise OSError("exec format error")

    monkeypatch.setattr(audio_player.subprocess, "Popen", _boom)

    assert play_wav(WAV, platform="linux") is False
    assert "Could not play" in caplog.text


def test_windows_path_uses_winsound(monkeypatch, spawned):
    """Windows bleibt bei winsound — stdlib, keine zusätzliche Abhängigkeit."""
    calls = []

    class _FakeWinsound:
        SND_FILENAME = 0x00020000
        SND_ASYNC = 0x0001

        @staticmethod
        def PlaySound(path, flags):
            calls.append((path, flags))

    monkeypatch.setattr(audio_player, "winsound", _FakeWinsound, raising=False)

    assert play_wav(WAV, block=False, platform="win32") is True
    path, flags = calls[0]
    assert path == str(WAV)
    assert flags & _FakeWinsound.SND_ASYNC  # nicht blockierend
    assert spawned["popen"] == []

    calls.clear()
    assert play_wav(WAV, block=True, platform="win32") is True
    _path, flags = calls[0]
    assert not flags & _FakeWinsound.SND_ASYNC


def test_windows_playback_error_is_swallowed(monkeypatch, caplog):
    class _BrokenWinsound:
        SND_FILENAME = 0x00020000
        SND_ASYNC = 0x0001

        @staticmethod
        def PlaySound(_path, _flags):
            raise RuntimeError("device busy")

    monkeypatch.setattr(audio_player, "winsound", _BrokenWinsound, raising=False)

    assert play_wav(WAV, platform="win32") is False
    assert "winsound" in caplog.text
