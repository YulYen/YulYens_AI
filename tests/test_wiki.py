# tests/test_wiki_proxy_lookup.py
import pytest

from tests.util import has_spacy_model
from core.streaming_provider import lookup_wiki_snippet
from wiki.spacy_keyword_finder import SpacyKeywordFinder, ModelVariant

pytestmark = pytest.mark.skipif(
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
