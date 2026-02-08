from pathlib import Path

if __package__:
    from .piper_tts import VOICES, synthesize
else:
    from piper_tts import VOICES, synthesize


if __name__ == "__main__":
    text = "Dies ist ein Test für die TTS-Funktion in Deutsch. Regenbögen und Einhörner sind Wörter. Wir sind Peter, Leah, Popcorn und Doris. Liebe Grüße an Julia K."
    voices_dir = Path("voices")
    out_dir = Path("out")

    for key in VOICES:
        out = out_dir / f"hallo_{key}.wav"
        synthesize(text, key, voices_dir, out)
        print(f"Wrote: {out}")
