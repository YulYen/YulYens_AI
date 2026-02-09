from pathlib import Path
import wave

from piper.voice import PiperVoice


def _resolve_model_name(persona: str, language: str, tts_cfg: dict) -> str:
    voices_cfg = tts_cfg["voices"]
    personas_de = voices_cfg.get("personas_de", {})

    if language == "de" and persona.upper() in personas_de:
        model_name = personas_de[persona.upper()]
    else:
        model_name = voices_cfg["default"][language]

    return model_name if model_name.endswith(".onnx") else f"{model_name}.onnx"


def create_wav(
    text: str,
    persona: str,
    voices_dir: Path,
    out_wav: Path,
    *,
    tts_cfg: dict,
    language: str = "de",
) -> None:
    model_name = _resolve_model_name(persona=persona, language=language, tts_cfg=tts_cfg)
    model_path = voices_dir / model_name

    if not model_path.exists():
        raise FileNotFoundError(model_path)

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    voice = PiperVoice.load(str(model_path))

    # WICHTIG: Piper setzt Header selbst – wave nur als Container
    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
