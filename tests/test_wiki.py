# tests/test_wiki_proxy_lookup.py
import logging
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from config.config_singleton import Config
from core.factory import AppFactory
from core.streaming_provider import lookup_wiki_snippet
from wiki.spacy_keyword_finder import SpacyKeywordFinder

from tests.util import has_spacy_model


class _DummyKeywordFinder:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def find_top_keyword(self, question: str) -> str:  # pragma: no cover - trivial
        return self._topic


def test_lookup_wiki_snippet_handles_network_errors(monkeypatch, caplog):
    """The wiki fallback informs the UI clearly about network errors."""

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
    """Even unexpected exceptions produce a UI fallback hint."""

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


def test_lookup_wiki_snippet_reflects_language_switch(monkeypatch, tmp_path):
    """A config reset with a language change is reflected in the wiki hints."""

    def _raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("proxy down")

    monkeypatch.setattr("core.streaming_provider.requests.get", _raise_connection_error)

    Config.reset_instance()
    Config("config.yaml")

    german_hint, _, _ = lookup_wiki_snippet(
        question="Frage?",
        persona_name="TEST",
        keyword_finder=_DummyKeywordFinder("Testthema"),
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
    )

    assert "Wikipedia-Proxy nicht erreichbar" in german_hint

    Config.reset_instance()

    custom_config_dir = tmp_path / "config"
    custom_config_dir.mkdir()
    shutil.copytree(
        Path(__file__).resolve().parent.parent / "locales",
        custom_config_dir / "locales",
    )
    english_config_path = custom_config_dir / "config.yaml"
    english_config_path.write_text('language: "en"\n', encoding="utf-8")

    Config(str(english_config_path))

    english_hint, _, _ = lookup_wiki_snippet(
        question="Question?",
        persona_name="TEST",
        keyword_finder=_DummyKeywordFinder("Testtopic"),
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
    )

    assert "Wikipedia proxy unreachable" in english_hint
    assert "Please check your connection" in english_hint

    Config.reset_instance()


def test_get_keyword_finder_handles_missing_spacy_model(monkeypatch):
    dummy_cfg = SimpleNamespace(wiki={"mode": "offline", "spacy_model_variant": "large", "spacy_modell_map": {}}, language="de")
    monkeypatch.setattr("core.factory.Config", lambda: dummy_cfg)

    try:
        factory = AppFactory()
        factory.get_keyword_finder()
        assert False # Fail if no Exception
    except ValueError as ve:
        assert "No spaCy model mapping for language='de', variant='large" in str(ve)


skip_without_medium_model = pytest.mark.skipif(
    not has_spacy_model("de_core_news_md"),
    reason="spaCy model de_core_news_md not installed",
)


@skip_without_medium_model
def test_lookup_wiki_snippet_for_germany():
    """
    Integration test: verifies that the local wiki proxy is running and
    returns a snippet for 'Deutschland' containing the capital 'Berlin'.
    """
    # KeywordFinder in medium mode (detects 'Deutschland')
    finder = SpacyKeywordFinder("de_core_news_md")

    # Assumptions: wiki_mode=offline, proxy runs locally on 8042, limit e.g. 1600
    wiki_hint, topic_title, snippet = lookup_wiki_snippet(
        question="Was ist die Hauptstadt von Deutschland?",
        persona_name="PETER",
        keyword_finder=finder,
        wiki_mode="offline",
        proxy_port=8042,
        limit=1600,
        timeout=(3.0, 8.0),
    )

    # We expect the proxy to be reachable and to detect 'Deutschland'
    assert (
        wiki_hint is not None and topic_title is not None # Hint could be an error-Message
    ), "Wiki proxy did not return a hint → it is probably not running"
    assert topic_title == "Deutschland"
    assert snippet, "Wiki proxy did not return any snippet text"

    # The capital Berlin should appear in the snippet (case-insensitive)
    assert "berlin" in snippet.lower()

