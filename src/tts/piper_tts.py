from pathlib import Path
import wave

from piper.voice import PiperVoice


VOICES = {
    "DORIS": "de_DE-kerstin-low.onnx",
    "POPCORN": "de_DE-pavoque-low.onnx",
    "LEAH": "de_DE-kerstin-low.onnx",
    "PETER": "de_DE-thorsten-high.onnx",
}

DEFAULT_VOICE = "de_DE-thorsten-high.onnx"


def synthesize(
    text: str,
    persona: str,
    voices_dir: Path,
    out_wav: Path,
) -> None:
    model_name = VOICES.get(persona, DEFAULT_VOICE)
    model_path = voices_dir / model_name

    if not model_path.exists():
        raise FileNotFoundError(model_path)

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    voice = PiperVoice.load(str(model_path))

    # WICHTIG: Piper setzt Header selbst – wave nur als Container
    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
