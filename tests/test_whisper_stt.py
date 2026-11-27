"""Tests für das optionale STT-Modul (#13) — faster-whisper wird gefakt."""

import sys
import types
from types import SimpleNamespace

import pytest
import yulyen_ai.stt.whisper_stt as whisper_stt


class _FakeWhisperModel:
    instances: list["_FakeWhisperModel"] = []

    def __init__(self, model_name, device="auto", compute_type="auto"):
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.transcribe_calls: list[dict] = []
        _FakeWhisperModel.instances.append(self)

    def transcribe(self, audio_path, language=None):
        self.transcribe_calls.append({"path": audio_path, "language": language})
        segments = [
            SimpleNamespace(text="  Hallo "),
            SimpleNamespace(text="Welt.  "),
        ]
        return iter(segments), SimpleNamespace(language=language)


def _install_fake_faster_whisper(monkeypatch):
    fake = types.ModuleType("faster_whisper")
    fake.WhisperModel = _FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake)
    monkeypatch.setattr(whisper_stt, "_model_cache", {})
    _FakeWhisperModel.instances = []


def test_transcribe_joins_and_strips_segments(monkeypatch):
    _install_fake_faster_whisper(monkeypatch)
    text = whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg={"language": "de"})
    assert text == "Hallo Welt."


def test_transcribe_passes_language_from_config(monkeypatch):
    _install_fake_faster_whisper(monkeypatch)
    whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg={"language": "de"})
    assert _FakeWhisperModel.instances[0].transcribe_calls[0]["language"] == "de"


def test_transcribe_null_language_means_autodetect(monkeypatch):
    _install_fake_faster_whisper(monkeypatch)
    whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg={"language": None})
    assert _FakeWhisperModel.instances[0].transcribe_calls[0]["language"] is None


def test_model_is_cached_per_config(monkeypatch):
    _install_fake_faster_whisper(monkeypatch)
    cfg = {"model": "small", "device": "auto", "compute_type": "auto"}
    whisper_stt.transcribe_wav("/tmp/a.wav", stt_cfg=cfg)
    whisper_stt.transcribe_wav("/tmp/b.wav", stt_cfg=cfg)
    assert len(_FakeWhisperModel.instances) == 1

    whisper_stt.transcribe_wav("/tmp/c.wav", stt_cfg={**cfg, "model": "tiny"})
    assert len(_FakeWhisperModel.instances) == 2
    assert _FakeWhisperModel.instances[1].model_name == "tiny"


# ---- Fehler, die erst beim Transkribieren auftauchen -------------------------

CUDA_ERROR = "Library cublas64_12.dll is not found or cannot be loaded"


def _failing_segments(exc: Exception):
    # Wie ctranslate2: transcribe() kehrt zurück, der Fehler kommt beim Iterieren.
    raise exc
    yield  # pragma: no cover — macht die Funktion zum Generator


class _GpuWithoutCudaLibs(_FakeWhisperModel):
    def transcribe(self, audio_path, language=None):
        if self.device != "cpu":
            self.transcribe_calls.append({"path": audio_path, "language": language})
            return _failing_segments(RuntimeError(CUDA_ERROR)), None
        return super().transcribe(audio_path, language)


def _install(monkeypatch, model_cls):
    _install_fake_faster_whisper(monkeypatch)
    sys.modules["faster_whisper"].WhisperModel = model_cls


def test_auto_device_falls_back_to_cpu_when_cuda_libs_are_missing(monkeypatch):
    """Der Fall von Yuls Kiste: GPU da, cuBLAS nicht — jede Aufnahme scheiterte."""
    _install(monkeypatch, _GpuWithoutCudaLibs)
    cfg = {"model": "small", "device": "auto", "compute_type": "auto"}

    assert whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg=cfg) == "Hallo Welt."
    assert [m.device for m in _FakeWhisperModel.instances] == ["auto", "cpu"]

    # Die zweite Aufnahme versucht die GPU nicht noch einmal.
    whisper_stt.transcribe_wav("/tmp/y.wav", stt_cfg=cfg)
    assert len(_FakeWhisperModel.instances) == 2
    assert _FakeWhisperModel.instances[0].transcribe_calls == [
        {"path": "/tmp/x.wav", "language": None}
    ]


def test_explicit_cuda_device_does_not_fall_back(monkeypatch):
    """Wer `cuda` sagt, hat entschieden — kein stiller Wechsel auf die CPU."""
    _install(monkeypatch, _GpuWithoutCudaLibs)
    cfg = {"device": "cuda"}

    with pytest.raises(RuntimeError, match="cublas64_12"):
        whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg=cfg)
    assert [m.device for m in _FakeWhisperModel.instances] == ["cuda"]


def test_unrelated_runtime_error_is_not_swallowed(monkeypatch):
    class _Broken(_FakeWhisperModel):
        def transcribe(self, audio_path, language=None):
            return _failing_segments(RuntimeError("out of memory")), None

    _install(monkeypatch, _Broken)
    with pytest.raises(RuntimeError, match="out of memory"):
        whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg={"device": "auto"})
    assert len(_FakeWhisperModel.instances) == 1


def test_pyav_19_error_names_the_remedy(monkeypatch):
    """Der rohe TypeError stand als Toast in der WebUI — ohne Hinweis, was hilft."""

    class _NewPyAv(_FakeWhisperModel):
        def transcribe(self, audio_path, language=None):
            raise TypeError(
                "open() got an unexpected keyword argument 'metadata_errors'"
            )

    _install(monkeypatch, _NewPyAv)
    with pytest.raises(RuntimeError, match=r'pip install "av<19"'):
        whisper_stt.transcribe_wav("/tmp/x.wav", stt_cfg={})


def test_is_stt_available_reflects_module_availability(monkeypatch):
    monkeypatch.setattr(whisper_stt, "module_available", lambda name: False)
    assert whisper_stt.is_stt_available() is False

    monkeypatch.setattr(whisper_stt, "module_available", lambda name: True)
    assert whisper_stt.is_stt_available() is True
