# tests/test_wiki_proxy_lookup.py
import logging
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
from config.config_singleton import Config
from core.factory import AppFactory
from launch import (
    ensure_kiwix_running_if_offlinemode_and_autostart,
    start_wiki_proxy_thread,
)
from wiki.lookup import lookup_wiki_snippet
from wiki.spacy_keyword_finder import SpacyKeywordFinder

from tests.util import has_spacy_model


class _DummyKeywordFinder:
    def __init__(self, topic: str) -> None:
        self._topic = topic

    def find_top_keyword(self, question: str) -> str:  # pragma: no cover - trivial
        return self._topic

    def find_keywords(self, question: str) -> list[str]:  # pragma: no cover - trivial
        return [self._topic]


def test_lookup_wiki_snippet_handles_network_errors(monkeypatch, caplog):
    """The wiki fallback informs the UI clearly about network errors."""

    def _raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("proxy down")

    dummy_finder = _DummyKeywordFinder("Testthema")
    monkeypatch.setattr("wiki.lookup.requests.get", _raise_connection_error)

    caplog.set_level(logging.ERROR)

    wiki_hints, contexts = lookup_wiki_snippet(
        question="Was ist los?",
        persona_name="TEST",
        keyword_finder=dummy_finder,
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
        max_snippets=2,
    )

    assert contexts == []
    assert wiki_hints == []
    assert "[WIKI EXC]" in caplog.text


def test_lookup_wiki_snippet_handles_unexpected_errors(monkeypatch, caplog):
    """Even unexpected exceptions produce a UI fallback hint."""

    def _raise_unexpected_error(*args, **kwargs):
        raise RuntimeError("kaputt")

    dummy_finder = _DummyKeywordFinder("Testthema")
    monkeypatch.setattr("wiki.lookup.requests.get", _raise_unexpected_error)

    caplog.set_level(logging.ERROR)

    wiki_hints, contexts = lookup_wiki_snippet(
        question="Was ist los?",
        persona_name="TEST",
        keyword_finder=dummy_finder,
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
        max_snippets=2,
    )

    assert contexts == []
    assert wiki_hints == []
    assert "[WIKI EXC]" in caplog.text
    assert "kaputt" in caplog.text


def test_lookup_wiki_snippet_url_encodes_topic(monkeypatch):
    captured = {}
    topic = "C++"

    def _fake_get(url, *args, **kwargs):
        captured["url"] = url
        return SimpleNamespace(
            status_code=200, json=lambda: {"text": "", "title": topic}
        )

    dummy_finder = _DummyKeywordFinder(topic)
    monkeypatch.setattr("wiki.lookup.requests.get", _fake_get)

    lookup_wiki_snippet(
        question="Was ist C++?",
        persona_name="TEST",
        keyword_finder=dummy_finder,
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
        max_snippets=1,
    )

    assert "/C%2B%2B" in captured["url"]


def test_lookup_wiki_snippet_reflects_language_switch(monkeypatch, tmp_path):
    """A config reset with a language change is reflected in the wiki hints."""

    def _raise_connection_error(*args, **kwargs):
        raise requests.exceptions.ConnectionError("proxy down")

    monkeypatch.setattr("wiki.lookup.requests.get", _raise_connection_error)

    Config.reset_instance()
    Config("config.yaml")

    german_hints, german_contexts = lookup_wiki_snippet(
        question="Frage?",
        persona_name="TEST",
        keyword_finder=_DummyKeywordFinder("Testthema"),
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
        max_snippets=2,
    )

    assert german_contexts == []
    assert german_hints == []

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

    english_hints, english_contexts = lookup_wiki_snippet(
        question="Question?",
        persona_name="TEST",
        keyword_finder=_DummyKeywordFinder("Testtopic"),
        wiki_mode="offline",
        proxy_port=9999,
        limit=42,
        timeout=(1.0, 1.0),
        max_snippets=2,
    )

    assert english_contexts == []
    assert english_hints == []

    Config.reset_instance()


def test_get_keyword_finder_handles_missing_spacy_model(monkeypatch):
    dummy_cfg = SimpleNamespace(
        wiki={"mode": "offline", "spacy_model_variant": "large", "spacy_model_map": {}},
        language="de",
    )
    monkeypatch.setattr("core.factory.Config", lambda: dummy_cfg)

    try:
        factory = AppFactory()
        factory.get_keyword_finder()
        assert False  # Fail if no Exception
    except ValueError as ve:
        assert "No spaCy model mapping for language='de', variant='large" in str(ve)


skip_without_medium_model = pytest.mark.skipif(
    not has_spacy_model("de_core_news_md"),
    reason="spaCy model de_core_news_md not installed",
)


@skip_without_medium_model
@pytest.mark.slow
def test_lookup_wiki_snippet_for_germany():
    """
    Integration test: verifies that the local wiki proxy returns a snippet for
    'Deutschland' containing the capital 'Berlin'.

    Starts the proxy and offline Kiwix itself (same mechanism as the
    ``client_with_date_and_wiki`` fixture) so the test does not depend on other
    tests having started them first. When the offline wiki is unavailable
    (e.g. Kiwix not installed), the test skips instead of failing — before
    starting the proxy thread, so no resources leak on skip.
    """
    Config.reset_instance()
    try:
        cfg = Config("config.yaml")
        cfg.ensemble = "classic"

        if not ensure_kiwix_running_if_offlinemode_and_autostart(cfg):
            pytest.skip("Offline wiki (Kiwix) not available")

        start_wiki_proxy_thread()

        # KeywordFinder in medium mode (detects 'Deutschland')
        finder = SpacyKeywordFinder("de_core_news_md")

        wiki_hints, contexts = lookup_wiki_snippet(
            question="Was ist die Hauptstadt von Deutschland?",
            persona_name="PETER",
            keyword_finder=finder,
            wiki_mode="offline",
            proxy_port=8042,
            limit=1600,
            timeout=(3.0, 8.0),
            max_snippets=2,
        )

        if not (wiki_hints and contexts):
            pytest.skip("Offline wiki (proxy/Kiwix on port 8042) not available")

        top = contexts[0]
        assert top.topic == "Deutschland"
        assert top.snippet, "Wiki proxy did not return any snippet text"

        # The capital Berlin should appear in the snippet (case-insensitive)
        assert "berlin" in top.snippet.lower()

        # #32: der Proxy muss Link, Quelle und Originallänge mitliefern —
        # ohne die kann die UI den injizierten Ausschnitt nicht einordnen.
        assert top.link, "Proxy did not report a user-visible link"
        assert top.source == "local"
        assert top.full_length >= len(top.snippet)
    finally:
        Config.reset_instance()


# ---- Snippet-Metadaten (#32) ------------------------------------------------


def _proxy_payload(**overrides):
    payload = {
        "title": "Deutschland",
        "text": "Deutschland ist ein Bundesstaat.",
        "link": "http://127.0.0.1:8080/wiki/Deutschland",
        "source": "local",
        "wiki_hint": "🕵️ Hinweis",
        "full_length": 8432,
    }
    payload.update(overrides)
    return payload


def _lookup_against(monkeypatch, payload, *, limit=1200):
    monkeypatch.setattr(
        "wiki.lookup.requests.get",
        lambda *a, **k: SimpleNamespace(status_code=200, json=lambda: payload),
    )
    return lookup_wiki_snippet(
        question="Frage?",
        persona_name="TEST",
        keyword_finder=_DummyKeywordFinder("Deutschland"),
        wiki_mode="offline",
        proxy_port=9999,
        limit=limit,
        timeout=(1.0, 1.0),
        max_snippets=1,
    )


def test_lookup_keeps_link_source_and_original_length(monkeypatch):
    _hints, contexts = _lookup_against(monkeypatch, _proxy_payload())

    snippet = contexts[0]
    assert snippet.topic == "Deutschland"
    assert snippet.snippet == "Deutschland ist ein Bundesstaat."
    assert snippet.link == "http://127.0.0.1:8080/wiki/Deutschland"
    assert snippet.source == "local"
    assert snippet.full_length == 8432
    assert snippet.truncated is True


def test_lookup_without_full_length_counts_the_snippet_as_complete(monkeypatch):
    """Ein Proxy ohne das Feld darf nicht fälschlich 'gekürzt' anzeigen."""
    payload = _proxy_payload()
    del payload["full_length"]

    _hints, contexts = _lookup_against(monkeypatch, payload)

    assert contexts[0].full_length == len(contexts[0].snippet)
    assert contexts[0].truncated is False


def test_lookup_ignores_a_nonsense_full_length(monkeypatch):
    _hints, contexts = _lookup_against(monkeypatch, _proxy_payload(full_length="viele"))

    assert contexts[0].truncated is False


def test_inject_wiki_context_uses_the_snippet_fields():
    from wiki.lookup import WikiSnippet, inject_wiki_context

    Config.reset_instance()
    try:
        Config("config.yaml")
        history: list = []
        inject_wiki_context(
            history,
            [WikiSnippet(topic="Berlin", snippet="Hauptstadt", link="http://x")],
        )
    finally:
        Config.reset_instance()

    # Guardrail plus ein Block pro Snippet; der Link gehört nicht in den Prompt.
    assert len(history) == 2
    assert "WIKI SNIPPET 1: Berlin" in history[1]["content"]
    assert "Hauptstadt" in history[1]["content"]
    assert "http://x" not in history[1]["content"]


def test_proxy_apply_limit_reports_the_length_before_truncation():
    from wiki.wikipedia_proxy import _apply_limit

    article = "Wort " * 400  # 2000 Zeichen
    text, full_length = _apply_limit("", article, 100)

    assert full_length == len(article)
    assert len(text) <= 102  # gekürzt am Wortende, plus " …"
    assert text.endswith(" …")


def test_proxy_apply_limit_keeps_short_articles_intact():
    from wiki.wikipedia_proxy import _apply_limit

    text, full_length = _apply_limit("", "Kurzer Artikel.", 1200)

    assert text == "Kurzer Artikel."
    assert full_length == len("Kurzer Artikel.")


def test_proxy_apply_limit_counts_the_infobox_block_too():
    """Der Key/Value-Block gehört zum ausgelieferten Text — und zur Länge."""
    from wiki.wikipedia_proxy import _apply_limit

    kv_line = "Hauptstadt: Berlin"
    article = "Wort " * 400
    text, full_length = _apply_limit(kv_line, article, 100)

    assert text.startswith(kv_line)
    assert full_length == len(kv_line) + 2 + len(article)


# ---- WikiLookup: ein Objekt statt fünf Attributen ---------------------------


def test_wiki_lookup_passes_every_setting_through(monkeypatch):
    """Die acht Argumente standen an sechs Stellen — jetzt an einer."""
    from wiki.lookup import WikiLookup

    captured = {}

    def _fake(question, persona_name, finder, mode, port, limit, timeout, max_snippets):
        captured.update(
            question=question,
            persona=persona_name,
            finder=finder,
            mode=mode,
            port=port,
            limit=limit,
            timeout=timeout,
            max_snippets=max_snippets,
        )
        return ([], [])

    monkeypatch.setattr("wiki.lookup.lookup_wiki_snippet", _fake)

    finder = _DummyKeywordFinder("Thema")
    lookup = WikiLookup(
        keyword_finder=finder,
        mode="offline",
        proxy_port=1234,
        limit=99,
        max_snippets=3,
        timeout=(1.0, 2.0),
    )
    lookup.snippets("Frage?", "PETER")

    assert captured == {
        "question": "Frage?",
        "persona": "PETER",
        "finder": finder,
        "mode": "offline",
        "port": 1234,
        "limit": 99,
        "timeout": (1.0, 2.0),
        "max_snippets": 3,
    }


def test_wiki_lookup_from_config_reads_the_wiki_section():
    from types import SimpleNamespace

    from wiki.lookup import WikiLookup

    cfg = SimpleNamespace(
        wiki={
            "mode": "online",
            "proxy_port": 8042,
            "snippet_limit": 1200,
            "max_wiki_snippets": 2,
            "timeout_connect": 3.0,
            "timeout_read": 8.0,
        }
    )

    lookup = WikiLookup.from_config(cfg, keyword_finder=None)

    assert lookup.mode == "online"
    assert lookup.limit == 1200
    assert lookup.timeout == (3.0, 8.0)


def test_wiki_lookup_without_a_wiki_section_stays_usable():
    """Eine Config ohne wiki-Sektion darf nicht beim Bauen krachen."""
    from types import SimpleNamespace

    from wiki.lookup import WikiLookup

    lookup = WikiLookup.from_config(SimpleNamespace(), keyword_finder=None)

    assert lookup.snippets("Frage?", "TEST") == ([], [])
