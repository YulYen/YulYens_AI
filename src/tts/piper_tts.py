from pathlib import Path
import wave

from piper.voice import PiperVoice


VOICES = {
    "DORIS": "de_DE-kerstin-low",
    "POPCORN": "de_DE-pavoque-low",
    "LEAH": "de_DE-kerstin-low",
    "PETER": "de_DE-thorsten-high",
}

_DEFAULT_TTS_CFG = {
    "voices": {
        "default": {"de": "de_DE-thorsten-high", "en": "en_US-amy-medium"},
        "personas_de": VOICES,
    }
}


def _resolve_model_name(persona: str, language: str, tts_cfg: dict) -> str:
    voices_cfg = tts_cfg["voices"]
    personas_de = voices_cfg.get("personas_de", {})

    if language == "de" and persona.upper() in personas_de:
        model_name = personas_de[persona.upper()]
    else:
        model_name = voices_cfg["default"][language]

    return model_name if model_name.endswith(".onnx") else f"{model_name}.onnx"


def synthesize(
    text: str,
    persona: str,
    voices_dir: Path,
    out_wav: Path,
    *,
    tts_cfg: dict | None = None,
    language: str = "de",
) -> None:
    resolved_tts_cfg = tts_cfg or _DEFAULT_TTS_CFG
    model_name = _resolve_model_name(persona=persona, language=language, tts_cfg=resolved_tts_cfg)
    model_path = voices_dir / model_name

    if not model_path.exists():
        raise FileNotFoundError(model_path)

    out_wav.parent.mkdir(parents=True, exist_ok=True)

    voice = PiperVoice.load(str(model_path))

    # WICHTIG: Piper setzt Header selbst – wave nur als Container
    with wave.open(str(out_wav), "wb") as wav_file:
        voice.synthesize_wav(text, wav_file)
