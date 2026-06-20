import sys
from pathlib import Path

if sys.platform == "win32":
    import winsound


def play_wav(path: Path, block: bool = False) -> None:
    if sys.platform != "win32":
        return
    flags = winsound.SND_FILENAME
    if not block:
        flags |= winsound.SND_ASYNC
    winsound.PlaySound(str(path), flags)
