from pathlib import Path
import wave

from piper.voice import PiperVoice


VOICES = {
    "DORIS": "de_DE-kerstin-low.onnx",
    "POPCORN": "de_DE-pavoque-low.onnx",
    "LEAH": "de_DE-mls-medium.onnx",
    "PETER": "de_DE-thorsten-high.onnx",
}

SPEAKER = {
    "DORIS": 0,
    "POPCORN": 0,
    "LEAH": 103,
    "PETER": 0,
}

DEFAULT_VOICE ="de_DE-thorsten-high.onnx"



def synthesize(text: str, voice_key: str, voices_dir: Path, out_wav: Path) -> None:
    model_path = voices_dir / VOICES[voice_key]
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    voice = PiperVoice.load(str(model_path))

    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
