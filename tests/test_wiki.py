# tests/test_wiki_proxy_lookup.py
import logging
from types import SimpleNamespace

import pytest
import requests

from tests.util import has_spacy_model
from core.factory import AppFactory
from core.streaming_provider import lookup_wiki_snippet
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant


class _DummyKeywordFinder:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def find_top_keyword(self, question: str) -> str:  # pragma: no cover - trivial
        return self._topic


def test_lookup_wiki_snippet_handles_network_errors(monkeypatch, caplog):
    """Der Wiki-Fallback informiert die UI verständlich über Netzwerkfehler."""

    def _raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("proxy down")

    dummy_finder = _DummyKeywordFinder("Testthema")
    monkeypatch.setattr("core.streaming_provider.requests.get", _raise_connection_error)

    caplog.set_level(logging.ERROR)

    wiki_hint, topic_title, snippet = lookup_wiki_snippet(
        question="Was ist los?",
        persona_name="TEST",
        keyword_finder=dummy_finder,
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
    )

    assert topic_title is None
    assert snippet is None
    assert "Wikipedia-Proxy nicht erreichbar" in wiki_hint
    assert "Bitte prüfe die Verbindung" in wiki_hint
    assert "[WIKI EXC]" in caplog.text


def test_lookup_wiki_snippet_handles_unexpected_errors(monkeypatch, caplog):
    """Selbst unerwartete Exceptions liefern einen UI-Fallback-Hinweis."""

    def _raise_unexpected_error(*args, **kwargs):
        raise RuntimeError("kaputt")

    dummy_finder = _DummyKeywordFinder("Testthema")
    monkeypatch.setattr("core.streaming_provider.requests.get", _raise_unexpected_error)

    caplog.set_level(logging.ERROR)

    wiki_hint, topic_title, snippet = lookup_wiki_snippet(
        question="Was ist los?",
        persona_name="TEST",
        keyword_finder=dummy_finder,
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
    )

    assert topic_title is None
    assert snippet is None
    assert "Unbekannter Fehler" in wiki_hint
    assert "[WIKI EXC]" in caplog.text
    assert "kaputt" in caplog.text


skip_without_medium_model = pytest.mark.skipif(
    not has_spacy_model("de_core_news_md"),
    reason="spaCy model de_core_news_md not installed",
)

@skip_without_medium_model
def test_lookup_wiki_snippet_for_germany():
    """
    Integrationstest: prüft, ob der lokale Wiki-Proxy läuft und
    zu 'Deutschland' ein Snippet mit Hauptstadt 'Berlin' liefert.
    """
    # KeywordFinder im Medium-Mode (findet 'Deutschland')
    finder = SpacyKeywordFinder(ModelVariant.MEDIUM)

    # Annahmen: wiki_mode=offline, Proxy läuft lokal auf 8042, Limit z. B. 1600
    wiki_hint, topic_title, snippet = lookup_wiki_snippet(
        question="Was ist die Hauptstadt von Deutschland?",
        persona_name="PETER",
        keyword_finder=finder,
        wiki_mode="offline",
        proxy_port=8042,
        limit=1600,
        timeout = (3.0, 8.0))

    # Wir erwarten, dass der Proxy erreichbar ist und 'Deutschland' erkannt wurde
    assert wiki_hint is not None, "Wiki-Proxy liefert keinen Hint → vermutlich nicht gestartet"
    assert topic_title == "Deutschland"
    assert snippet, "Wiki-Proxy liefert keinen Snippet-Text"

    # Hauptstadt Berlin sollte im Snippet vorkommen (Groß-/Kleinschreibung egal)
    assert "berlin" in snippet.lower()


def _capture_variant(monkeypatch, wiki_config):
    dummy_cfg = SimpleNamespace(wiki=wiki_config)

    monkeypatch.setattr("core.factory.Config", lambda: dummy_cfg)

    captured = {}

    class DummyFinder:
        def __init__(self, variant):
            captured["variant"] = variant

    monkeypatch.setattr("core.factory.SpacyKeywordFinder", DummyFinder)

    factory = AppFactory()
    finder = factory.get_keyword_finder()

    assert isinstance(finder, DummyFinder)
    return captured["variant"]


def test_get_keyword_finder_uses_medium_variant(monkeypatch):
    variant = _capture_variant(
        monkeypatch,
        {"mode": "offline", "spacy_model_variant": "medium"},
    )

    assert variant is ModelVariant.MEDIUM


def test_get_keyword_finder_supports_model_name(monkeypatch):
    variant = _capture_variant(
        monkeypatch,
        {"mode": "offline", "spacy_model_variant": "de_core_news_md"},
    )

    assert variant is ModelVariant.MEDIUM


def test_get_keyword_finder_falls_back_to_large(monkeypatch):
    variant = _capture_variant(
        monkeypatch,
        {"mode": "offline", "spacy_model_variant": "unbekannt"},
    )

    assert variant is ModelVariant.LARGE


def test_get_keyword_finder_defaults_when_missing(monkeypatch):
    variant = _capture_variant(
        monkeypatch,
        {"mode": "offline"},
    )

    assert variant is ModelVariant.LARGE


def test_get_keyword_finder_accepts_enum_value(monkeypatch):
    variant = _capture_variant(
        monkeypatch,
        {"mode": "offline", "spacy_model_variant": ModelVariant.MEDIUM},
    )

    assert variant is ModelVariant.MEDIUM
