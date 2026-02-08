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
    cfg = {"voices": {"default": {"de": "de_DE-thorsten-high", "en": "en_US-amy-medium"}}}
    assert _resolve_model_name("UNKNOWN", "en", cfg) == "en_US-amy-medium.onnx"


def test_resolve_model_name_falls_back_to_german_default_without_personas_de() -> None:
    cfg = {"voices": {"default": {"de": "de_DE-thorsten-high", "en": "en_US-amy-medium"}}}
    assert _resolve_model_name("LEAH", "de", cfg) == "de_DE-thorsten-high.onnx"


def test_synthesize_keeps_backward_compatible_signature(tmp_path) -> None:
    from tts.piper_tts import synthesize

    try:
        synthesize("Hallo", "LEAH", tmp_path, tmp_path / "out.wav")
    except FileNotFoundError as exc:
        assert "de_DE-kerstin-low.onnx" in str(exc)
    else:
        raise AssertionError("Expected missing voice file to raise FileNotFoundError")
