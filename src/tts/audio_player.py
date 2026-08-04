"""Playing a WAV file, on whatever platform happens to be running (#34).

Windows keeps using winsound (stdlib, no extra dependency). Linux and macOS get
a dispatch to the usual command-line players, which are present on virtually
every desktop install — still zero new dependencies.

Fails silently by design: audio is a nice-to-have here. A missing player must
not take down a terminal chat, so every failure is logged and swallowed. The
return value says whether playback actually started, which is what the tests
assert on.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

if sys.platform == "win32":  # pragma: no cover - platform specific
    import winsound
else:
    # Der Name muss auf *jeder* Plattform existieren: `play_wav` entscheidet
    # über eine Laufzeit-Variable (`platform`, damit die Verteilung testbar
    # ist), und die Tests stellen den Windows-Zweig auf Linux nach, indem sie
    # dieses Attribut ersetzen. Für mypy ist der Zweig hier der einzige, den es
    # auf Linux sieht — unter `mypy --platform win32` nimmt es den echten
    # Import oben und prüft die winsound-Aufrufe wirklich.
    winsound: Any = None

# First match wins. paplay covers PulseAudio/PipeWire, aplay plain ALSA;
# ffplay is the fallback for boxes that have ffmpeg but no sound tooling.
_LINUX_PLAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("paplay", ()),
    ("aplay", ("-q",)),
    ("ffplay", ("-nodisp", "-autoexit", "-loglevel", "quiet")),
)
_MACOS_PLAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (("afplay", ()),)


def _candidates(platform: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if platform == "darwin":
        return _MACOS_PLAYERS
    if platform.startswith("linux"):
        return _LINUX_PLAYERS
    return ()


def find_player(platform: str | None = None) -> tuple[str, tuple[str, ...]] | None:
    """The first available CLI player for this platform, or None."""
    for name, args in _candidates(platform or sys.platform):
        binary = shutil.which(name)
        if binary:
            return binary, args
    return None


def play_wav(path: Path, block: bool = False, platform: str | None = None) -> bool:
    """Play ``path``. Returns True when playback was started.

    ``platform`` exists so the dispatch can be tested without the platform.
    """
    current = platform or sys.platform
    wav = Path(path)

    if current == "win32":  # pragma: no cover - platform specific
        # Ausdrücklich `int`: typeshed gibt SND_FILENAME als Literal[131072],
        # und das nächste `|=` macht daraus wieder ein gewöhnliches int.
        flags: int = winsound.SND_FILENAME
        if not block:
            flags |= winsound.SND_ASYNC
        try:
            winsound.PlaySound(str(wav), flags)
            return True
        except RuntimeError as exc:
            logging.warning("Could not play %s via winsound: %s", wav, exc)
            return False

    player = find_player(current)
    if player is None:
        # Kein Fehler, nur nichts zu tun — z. B. headless ohne Audio-Tooling.
        logging.info(
            "No audio player found for platform %s (tried: %s) — skipping playback.",
            current,
            ", ".join(name for name, _ in _candidates(current)) or "none",
        )
        return False

    binary, args = player
    command = [binary, *args, str(wav)]
    try:
        if block:
            subprocess.run(command, check=False, capture_output=True)
        else:
            # Ohne wait(): der Terminal-Chat soll weiterlaufen. stdout/stderr
            # in DEVNULL, damit der Player die Konsole nicht zumüllt.
            subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        return True
    except OSError as exc:
        logging.warning("Could not play %s via %s: %s", wav, binary, exc)
        return False
