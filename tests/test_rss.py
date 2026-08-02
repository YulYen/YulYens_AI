"""RSS als Kontextquelle (#73) — HTTP wird an der Modulgrenze gefakt.

**Kein Test hier greift je ins Netz.** Der Cache holt nur in ``refresh()``,
und das wird in jedem Fall unten mit einem gefälschten ``requests.get``
aufgerufen — oder gar nicht.
"""

from datetime import datetime

import pytest
import requests
from config.config_singleton import Config
from rss.feeds import (
    RssCache,
    RssItem,
    _parse_feed,
    build_context_block,
    build_rss_cache,
    inject_rss_context,
)

from tests.doubles import permissive_guard_double

RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Testfeed</title>
    <item>
      <title>Erste Meldung</title>
      <description>&lt;p&gt;Text mit &lt;b&gt;HTML&lt;/b&gt; drin.&lt;/p&gt;</description>
      <pubDate>Wed, 30 Jul 2026 08:15:00 +0200</pubDate>
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
    <updated>2026-07-30T06:15:00Z</updated>
  </entry>
</feed>
"""


@pytest.fixture(autouse=True)
def _texts():
    """Locale-Texte, damit `Config().t(...)` in den Bausteinen funktioniert."""
    Config.reset_instance()
    Config("config.yaml")
    yield
    Config.reset_instance()


def _cache(**overrides) -> RssCache:
    params = {
        "feeds": [{"name": "testfeed", "url": "https://example.org/feed"}],
        "max_items_per_feed": 2,
        "max_chars_per_item": 400,
    }
    params.update(overrides)
    return RssCache(**params)


def _fake_get(monkeypatch, text=RSS_SAMPLE, status=200):
    calls = []

    class _Response:
        def __init__(self):
            self.text = text
            self.status_code = status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.exceptions.HTTPError(f"status {self.status_code}")

    def _get(url, **kwargs):
        calls.append((url, kwargs))
        return _Response()

    monkeypatch.setattr(requests, "get", _get)
    return calls


# ---- Parsen ----------------------------------------------------------------


def test_rss_items_carry_their_publication_date():
    """Ohne Datum sagt das Modell „heute" über Vorgestern (#73).

    `_parse_feed` las bisher nur Titel und Text — für eine Nachrichtenquelle
    ist das der Unterschied zwischen Quelle und Gerücht.
    """
    items = _parse_feed(RSS_SAMPLE, "testfeed", max_items=3)

    assert items[0].published is not None
    assert items[0].published.strftime("%d.%m.%Y") == "30.07.2026"
    # Ein Item ohne pubDate ist kein Fehler, nur undatiert.
    assert items[1].published is None


def test_atom_dates_are_read_too():
    items = _parse_feed(ATOM_SAMPLE, "atomfeed", max_items=3)
    assert items[0].published is not None
    assert items[0].title == "Atom-Meldung"


def test_html_is_reduced_and_the_limit_holds():
    items = _parse_feed(RSS_SAMPLE, "testfeed", max_items=2)
    assert len(items) == 2
    assert "<b>" not in items[0].body
    assert "HTML" in items[0].body


def test_broken_xml_is_a_value_error():
    with pytest.raises(ValueError):
        _parse_feed("<rss><channel>", "testfeed", max_items=2)


def test_a_line_carries_source_and_stamp():
    item = RssItem(
        source="tagesschau",
        title="Titel",
        body="Text",
        published=datetime(2026, 7, 30, 8, 15),
    )
    line = item.as_line(max_chars=400)
    assert line.startswith("[tagesschau, 30.07. 08:15]")
    assert "Titel" in line and "Text" in line


def test_a_long_item_is_cut_to_the_budget():
    item = RssItem(source="s", title="", body="A" * 900)
    line = item.as_line(max_chars=100)
    assert "A" * 101 not in line
    assert line.endswith("[…]")


# ---- Cache -----------------------------------------------------------------


def test_the_cache_fills_from_the_feed(monkeypatch):
    calls = _fake_get(monkeypatch)
    cache = _cache()

    cache.refresh()

    assert len(calls) == 1
    assert len(cache.items_for(["testfeed"])) == 2
    assert cache.filled_at is not None


def test_asking_the_cache_never_touches_the_network(monkeypatch):
    """Der Kern der Entscheidung gegen einen Lazy-Load (#73).

    Ein Turn nimmt, was da ist. Holte `items_for` selbst nach, zahlte genau die
    Frage, die nach Ablauf der Frist zuerst kommt, die volle Netz-Latenz — das
    ist die Falle, die #51 vier Sekunden gekostet hat.
    """

    def _boom(*_a, **_kw):
        raise AssertionError("items_for darf niemals ins Netz greifen")

    monkeypatch.setattr(requests, "get", _boom)
    cache = _cache()

    assert cache.items_for(["testfeed"]) == []
    assert cache.filled_at is None


def test_a_failing_feed_keeps_the_last_good_items(monkeypatch):
    """Eine Minute Netzausfall darf die Meldungen von vorhin nicht löschen."""
    _fake_get(monkeypatch)
    cache = _cache()
    cache.refresh()
    assert len(cache.items_for(["testfeed"])) == 2

    def _fail(*_a, **_kw):
        raise requests.exceptions.ConnectionError("weg")

    monkeypatch.setattr(requests, "get", _fail)
    cache.refresh()

    assert len(cache.items_for(["testfeed"])) == 2
    assert "testfeed" in cache.failed_feeds()


def test_a_disabled_section_builds_an_empty_cache():
    """Leerer Cache statt None — die Oberflächen fragen ohne Fallunterscheidung."""
    cache = build_rss_cache({"enabled": False, "feeds": [{"name": "x", "url": "u"}]})
    assert cache.feed_names == []
    assert cache.items_for(["x"]) == []


def test_the_cache_reads_its_settings_from_the_section():
    cache = build_rss_cache(
        {
            "enabled": True,
            "feeds": [{"name": "a", "url": "u"}],
            "max_items_per_feed": 7,
            "max_chars_per_item": 111,
            "refresh_minutes": 15,
        }
    )
    assert (cache.max_items_per_feed, cache.max_chars_per_item) == (7, 111)
    assert cache.refresh_minutes == 15


# ---- Kontext-Block ---------------------------------------------------------


def _items():
    return [
        RssItem("tagesschau", "Erste", "Text eins", datetime(2026, 7, 30, 8, 0)),
        RssItem("heise online", "Zweite", "Text zwei", datetime(2026, 7, 30, 9, 0)),
    ]


def test_everything_becomes_one_block():
    """Vorher war jedes Item eine eigene System-Nachricht (#73).

    Bei 2 Feeds × 4 Items waren das neun System-Nachrichten ohne
    Zeichenbudget — in einem 8k-Fenster.
    """
    cache = _cache()
    cache._filled_at = datetime(2026, 7, 30, 10, 30).timestamp()
    block, dropped = build_context_block(_items(), cache, guard=None)

    history: list = []
    inject_rss_context(history, block)

    assert dropped == 0
    assert len(history) == 2  # Guardrail + genau ein Block
    assert history[0]["role"] == "system" and history[1]["role"] == "system"
    assert "Erste" in history[1]["content"] and "Zweite" in history[1]["content"]
    assert "10:30" in history[1]["content"], "der Stand gehört an den Block"


def test_the_guard_filters_per_item_before_merging():
    """Sonst reißt eine schräge Schlagzeile den ganzen Block mit (#73).

    Derselbe Fehler wie damals bei `WikiLookup.snippets()`, nur andersherum:
    dort wurde zu spät gefiltert, hier wäre zu grob gefiltert worden.
    """

    guard = permissive_guard_double()
    guard.check_input.side_effect = lambda text: (
        {"ok": True, "reason": "ok", "detail": None}
        if "Zweite" not in text
        else {"ok": False, "reason": "prompt_injection", "detail": ""}
    )

    cache = _cache()
    block, dropped = build_context_block(_items(), cache, guard=guard)

    assert dropped == 1
    assert "Erste" in block
    assert "Zweite" not in block


def test_nothing_left_after_the_guard_means_no_block():
    guard = permissive_guard_double()
    guard.check_input.return_value = {
        "ok": False,
        "reason": "prompt_injection",
        "detail": "",
    }

    block, dropped = build_context_block(_items(), _cache(), guard=guard)
    history: list = []
    inject_rss_context(history, block)

    assert block is None
    assert dropped == 2
    assert history == []


def test_an_empty_block_injects_nothing():
    history: list = []
    inject_rss_context(history, None)
    assert history == []


def test_a_permissive_guard_lets_everything_through():
    """Gegenrichtung: ohne Befund darf nichts verloren gehen."""
    block, dropped = build_context_block(
        _items(), _cache(), guard=permissive_guard_double()
    )
    assert block and dropped == 0
