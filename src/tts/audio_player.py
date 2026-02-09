from pathlib import Path
import winsound

# Windows-only
def play_wav(path: Path, block: bool = False) -> None:
    flags = winsound.SND_FILENAME
    if not block:
        flags |= winsound.SND_ASYNC
    winsound.PlaySound(str(path), flags)