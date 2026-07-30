"""Tests für das optionale STT-Modul (#13) — faster-whisper wird gefakt."""

import sys
import types
from types import SimpleNamespace

import stt.whisper_stt as whisper_stt


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


def test_is_stt_available_reflects_find_spec(monkeypatch):
    monkeypatch.setattr(whisper_stt.importlib.util, "find_spec", lambda name: None)
    assert whisper_stt.is_stt_available() is False

    monkeypatch.setattr(whisper_stt.importlib.util, "find_spec", lambda name: object())
    assert whisper_stt.is_stt_available() is True
