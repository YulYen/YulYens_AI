# tests/test_wiki_proxy_lookup.py
import logging

import pytest

from tests.util import has_spacy_model
from core.streaming_provider import lookup_wiki_snippet
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant
from core.factory import AppFactory
from config.config_singleton import Config


def test_spacy_keyword_finder_reports_missing_model(monkeypatch):
    def fake_load(_model_name):
        raise OSError("model missing")

    monkeypatch.setattr("wiki.spacy_keyword_finder.spacy.load", fake_load)

    with pytest.raises(
        RuntimeError,
        match=r"SpaCy-Modell 'de_core_news_md' konnte nicht geladen werden",
    ):
        SpacyKeywordFinder(ModelVariant.MEDIUM)


def test_app_factory_disables_wiki_when_spacy_missing(monkeypatch, caplog):
    Config.reset_instance()
    try:
        factory = AppFactory()

        calls = []

        def fake_load(model_name):
            calls.append(model_name)
            raise OSError("no model installed")

        monkeypatch.setattr("wiki.spacy_keyword_finder.spacy.load", fake_load)
        caplog.set_level(logging.WARNING, logger="core.factory")

        finder = factory.get_keyword_finder()

        assert finder is None
        assert calls == [ModelVariant.LARGE.value]
        assert factory.get_config().wiki["mode"] is False
        assert "kein Wiki" in caplog.text

        second = factory.get_keyword_finder()

        assert second is None
        assert calls == [ModelVariant.LARGE.value]
    finally:
        Config.reset_instance()


@pytest.mark.skipif(
    not has_spacy_model("de_core_news_md"),
    reason="spaCy model de_core_news_md not installed",
)
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
