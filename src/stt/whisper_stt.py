import importlib.util
import logging
from typing import Any

# WhisperModel-Instanzen sind teuer (Laden dauert Sekunden) — pro
# (model, device, compute_type) genau einmal instanziieren und behalten.
_model_cache: dict[tuple[str, str, str], Any] = {}


def is_stt_available() -> bool:
    """True, wenn faster-whisper installiert ist (ohne es zu importieren)."""
    return importlib.util.find_spec("faster_whisper") is not None


def _get_model(stt_cfg: dict) -> Any:
    model_name = str(stt_cfg.get("model", "small"))
    device = str(stt_cfg.get("device", "auto"))
    compute_type = str(stt_cfg.get("compute_type", "auto"))
    key = (model_name, device, compute_type)
    if key not in _model_cache:
        # Lazy: faster-whisper ist wie piper-tts eine optionale Abhängigkeit
        from faster_whisper import WhisperModel

        logging.info("STT: lade Whisper-Modell '%s' (%s/%s)", *key)
        _model_cache[key] = WhisperModel(
            model_name, device=device, compute_type=compute_type
        )
    return _model_cache[key]


def transcribe_wav(audio_path: str, *, stt_cfg: dict) -> str:
    """Transkribiert eine Audiodatei lokal; language: null = Auto-Erkennung."""
    model = _get_model(stt_cfg)
    language = stt_cfg.get("language") or None
    segments, _info = model.transcribe(audio_path, language=language)
    return " ".join(segment.text.strip() for segment in segments).strip()
