from pathlib import Path
import wave

from piper.voice import PiperVoice


VOICES = {
    "kerstin": "de_DE-kerstin-low.onnx",
    "karlsson": "de_DE-karlsson-low.onnx",
    "pavoque": "de_DE-pavoque-low.onnx",
    "thorsten": "de_DE-thorsten-high.onnx",
}


def synthesize(text: str, voice_key: str, voices_dir: Path, out_wav: Path) -> None:
    model_path = voices_dir / VOICES[voice_key]
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    voice = PiperVoice.load(str(model_path))

    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
