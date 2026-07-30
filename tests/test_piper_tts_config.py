import sys
import types


class _DummyPiperVoice:
    @staticmethod
    def load(_path: str):
        return object()


piper_module = types.ModuleType("piper")
voice_module = types.ModuleType("piper.voice")
voice_module.PiperVoice = _DummyPiperVoice
sys.modules.setdefault("piper", piper_module)
sys.modules["piper.voice"] = voice_module

from pathlib import Path

from tts import piper_tts
from tts.piper_tts import _resolve_model_name


def test_resolve_model_name_uses_german_persona_override() -> None:
    cfg = {
        "voices": {
            "default": {"de": "de_DE-thorsten-high", "en": "en_US-amy-medium"},
            "personas_de": {"LEAH": "de_DE-kerstin-low"},
        }
    }
    assert _resolve_model_name("LEAH", "de", cfg) == "de_DE-kerstin-low.onnx"


def test_resolve_model_name_uses_language_default() -> None:
    cfg = {
        "voices": {"default": {"de": "de_DE-thorsten-high", "en": "en_US-amy-medium"}}
    }
    assert _resolve_model_name("UNKNOWN", "en", cfg) == "en_US-amy-medium.onnx"


def test_resolve_model_name_falls_back_to_german_default_without_personas_de() -> None:
    cfg = {
        "voices": {"default": {"de": "de_DE-thorsten-high", "en": "en_US-amy-medium"}}
    }
    assert _resolve_model_name("LEAH", "de", cfg) == "de_DE-thorsten-high.onnx"


def test_load_voice_caches_per_model_path(monkeypatch) -> None:
    loads: list[str] = []
    monkeypatch.setattr(
        piper_tts.PiperVoice,
        "load",
        staticmethod(lambda path: loads.append(path) or object()),
    )
    monkeypatch.setattr(piper_tts, "_voice_cache", {})

    first = piper_tts._load_voice(Path("voices/a.onnx"))
    second = piper_tts._load_voice(Path("voices/a.onnx"))

    assert first is second
    assert len(loads) == 1

    piper_tts._load_voice(Path("voices/b.onnx"))
    assert len(loads) == 2
