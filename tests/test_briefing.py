"""Tests für das RSS-Briefing (#15) — HTTP wird an der Modulgrenze gefakt."""

from types import SimpleNamespace

import pytest
import requests
from briefing.feeds import _parse_feed, fetch_briefing_items, inject_briefing_context
from config.config_singleton import Config

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Testfeed</title>
    <item>
      <title>Erste Meldung</title>
      <description>&lt;p&gt;Text mit &lt;b&gt;HTML&lt;/b&gt; drin.&lt;/p&gt;</description>
      <link>https://example.org/1</link>
    </item>
    <item>
      <title>Zweite Meldung</title>
      <description>Schlichter Text.</description>
    </item>
    <item>
      <title>Dritte Meldung</title>
      <description>Kommt bei max_items=2 nicht mehr mit.</description>
    </item>
  </channel>
</rss>
"""

ATOM_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom-Testfeed</title>
  <entry>
    <title>Atom-Meldung</title>
    <summary>Zusammenfassung aus dem Atom-Feed.</summary>
    <link href="https://example.org/atom/1"/>
  </entry>
</feed>
"""


@pytest.fixture()
def de_config():
    Config.reset_instance()
    cfg = Config("config.yaml")
    yield cfg
    Config.reset_instance()


# ---- Parsing ----------------------------------------------------------------


def test_parse_feed_rss_strips_html_and_limits_items():
    items = _parse_feed(RSS_SAMPLE, max_items=2)
    assert items == [
        ("Erste Meldung", "Text mit HTML drin."),
        ("Zweite Meldung", "Schlichter Text."),
    ]


def test_parse_feed_atom_reads_entries_and_summary():
    items = _parse_feed(ATOM_SAMPLE, max_items=5)
    assert items == [("Atom-Meldung", "Zusammenfassung aus dem Atom-Feed.")]


def test_parse_feed_invalid_xml_raises_value_error():
    with pytest.raises(ValueError):
        _parse_feed("das ist kein XML <", max_items=3)


# ---- Fetch ------------------------------------------------------------------


def _feed_cfg():
    return {
        "max_items_per_feed": 2,
        "feeds": [
            {"name": "rss-quelle", "url": "https://example.org/rss"},
            {"name": "atom-quelle", "url": "https://example.org/atom"},
        ],
    }


def test_fetch_briefing_items_collects_all_feeds(monkeypatch, de_config):
    responses = {
        "https://example.org/rss": RSS_SAMPLE,
        "https://example.org/atom": ATOM_SAMPLE,
    }

    def _fake_get(url, timeout=None, headers=None):
        return SimpleNamespace(
            status_code=200, text=responses[url], raise_for_status=lambda: None
        )

    monkeypatch.setattr("briefing.feeds.requests.get", _fake_get)

    hints, items = fetch_briefing_items(_feed_cfg(), "KARL", timeout=(1.0, 1.0))

    assert len(hints) == 2
    assert "KARL" in hints[0] and "rss-quelle" in hints[0]
    sources = [source for source, _ in items]
    assert sources == [
        "rss-quelle: Erste Meldung",
        "rss-quelle: Zweite Meldung",
        "atom-quelle: Atom-Meldung",
    ]


def test_fetch_briefing_items_skips_broken_feed(monkeypatch, de_config):
    def _fake_get(url, timeout=None, headers=None):
        if url.endswith("/rss"):
            raise requests.exceptions.ConnectionError("feed down")
        return SimpleNamespace(
            status_code=200, text=ATOM_SAMPLE, raise_for_status=lambda: None
        )

    monkeypatch.setattr("briefing.feeds.requests.get", _fake_get)

    hints, items = fetch_briefing_items(_feed_cfg(), "KARL", timeout=(1.0, 1.0))

    assert len(hints) == 2
    assert "rss-quelle" in hints[0]  # Failed-Hint für den kaputten Feed
    assert [source for source, _ in items] == ["atom-quelle: Atom-Meldung"]


def test_fetch_briefing_items_without_feeds_is_empty(monkeypatch, de_config):
    def _boom(*args, **kwargs):  # darf nie aufgerufen werden
        raise AssertionError("no HTTP call expected")

    monkeypatch.setattr("briefing.feeds.requests.get", _boom)

    assert fetch_briefing_items({}, "KARL", timeout=(1.0, 1.0)) == ([], [])
    assert fetch_briefing_items({"feeds": []}, "KARL", timeout=(1.0, 1.0)) == ([], [])


# ---- Injection --------------------------------------------------------------


def test_inject_briefing_context_appends_guardrail_and_items(de_config):
    history = [{"role": "user", "content": "Hallo"}]
    items = [("quelle: Titel A", "Text A"), ("quelle: Titel B", "Text B")]

    inject_briefing_context(history, items)

    assert len(history) == 4
    assert history[1]["role"] == "system"  # Guardrail
    assert history[2]["role"] == "system"
    assert "=== BRIEFING 1: quelle: Titel A ===" in history[2]["content"]
    assert "Text A" in history[2]["content"]
    assert "=== BRIEFING 2: quelle: Titel B ===" in history[3]["content"]


def test_inject_briefing_context_noop_without_items(de_config):
    history = [{"role": "user", "content": "Hallo"}]
    inject_briefing_context(history, [])
    assert history == [{"role": "user", "content": "Hallo"}]
