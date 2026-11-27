"""Spracheingabe über faster-whisper (#13) — optional, lokal, ohne System-ffmpeg.

**`device: auto` weicht auf die CPU aus, wenn die CUDA-Bibliotheken fehlen.**
faster-whisper wählt bei vorhandener NVIDIA-Karte die GPU, prüft aber nicht, ob
ctranslate2 dort seine cuBLAS/cuDNN-DLLs findet. Fehlen sie, scheitert erst die
Transkription selbst (`Library cublas64_12.dll is not found …`) — jede Aufnahme,
während das Mikrofon ganz normal aussieht. So lief es auf Yuls Kiste drei
Wochen lang. Wer `device: cuda` ausdrücklich setzt, bekommt den Fehler dagegen
zu sehen: dort wäre ein stiller Wechsel auf die CPU eine Entscheidung, die
niemand getroffen hat.

**PyAV ≥ 19 passt nicht zu faster-whisper 1.2.1** (`av.open()` kennt
`metadata_errors` nicht mehr). faster-whisper deckelt `av` nicht, also holt ein
frisches `pip install faster-whisper` die kaputte Kombination. Der Fehler wird
hier in einen Satz mit dem Gegenmittel übersetzt, weil die WebUI ihn als Toast
zeigt und der rohe `TypeError` dort niemandem hilft.
"""

import logging
import re
from typing import Any

from yulyen_ai.core.utils import module_available

# WhisperModel-Instanzen sind teuer (Laden dauert Sekunden) — pro
# (model, device, compute_type) genau einmal instanziieren und behalten.
_model_cache: dict[tuple[str, str, str], Any] = {}

# ctranslate2 meldet eine fehlende CUDA-Laufzeit als RuntimeError mit dem
# Dateinamen: `cublas64_12.dll` unter Windows, `libcublas.so.12` unter Linux.
_MISSING_CUDA_LIBRARY = re.compile(r"(cublas|cudnn|cudart)\w*\.(dll|so)", re.I)

PYAV_HINT = (
    'PyAV 19 or newer does not work with faster-whisper — run: pip install "av<19"'
)


def is_stt_available() -> bool:
    """True, wenn faster-whisper installiert ist (ohne es zu importieren)."""
    return module_available("faster_whisper")


def _settings(stt_cfg: dict) -> tuple[str, str, str]:
    return (
        str(stt_cfg.get("model", "small")),
        str(stt_cfg.get("device", "auto")),
        str(stt_cfg.get("compute_type", "auto")),
    )


def _load(model_name: str, device: str, compute_type: str) -> Any:
    # Lazy: faster-whisper ist wie piper-tts eine optionale Abhängigkeit
    from faster_whisper import WhisperModel

    logging.info(
        "STT: lade Whisper-Modell '%s' (%s/%s)", model_name, device, compute_type
    )
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _get_model(stt_cfg: dict) -> Any:
    key = _settings(stt_cfg)
    if key not in _model_cache:
        _model_cache[key] = _load(*key)
    return _model_cache[key]


def _run(model: Any, audio_path: str, language: str | None) -> str:
    # `segments` ist ein Generator: die eigentliche Arbeit — und damit auch
    # der CUDA-Fehler — passiert erst beim Durchlaufen, deshalb hier drin.
    segments, _info = model.transcribe(audio_path, language=language)
    return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_wav(audio_path: str, *, stt_cfg: dict) -> str:
    """Transkribiert eine Audiodatei lokal; language: null = Auto-Erkennung."""
    language = stt_cfg.get("language") or None
    key = _settings(stt_cfg)
    model = _get_model(stt_cfg)
    try:
        return _run(model, audio_path, language)
    except TypeError as exc:
        if "metadata_errors" not in str(exc):
            raise
        raise RuntimeError(PYAV_HINT) from exc
    except RuntimeError as exc:
        model_name, device, compute_type = key
        if device != "auto" or not _MISSING_CUDA_LIBRARY.search(str(exc)):
            raise
        logging.warning(
            "STT: GPU nicht nutzbar (%s) — weiche auf die CPU aus. "
            "Dauerhaft: stt.device: cpu, oder die CUDA-12-Laufzeit installieren.",
            exc,
        )
        # Unter dem auto-Schlüssel ablegen: die nächste Aufnahme geht direkt
        # auf die CPU, statt jedes Mal erst an der GPU zu scheitern.
        _model_cache[key] = _load(model_name, "cpu", compute_type)
        return _run(_model_cache[key], audio_path, language)
