"""RSS/Atom als Kontextquelle für die Personas (#73).

Spiegelt bewusst die Wiki-Pipeline (``wiki/lookup.py``): eine Quelle, die sich
meldet, wenn die Frage danach ist — nicht ein Knopf, der alles abkippt.

**Geholt wird im Hintergrund, nie im Request-Pfad.** ``RssCache`` hält je
Quelle die neuesten Meldungen im Speicher und frischt sie beim Start und dann
alle ``rss.refresh_minutes`` auf. Ein Turn nimmt, was da ist — auch nichts.
Ein Lazy-Load wäre der Rückfall: dann wartet die erste Frage nach Ablauf doch
wieder auf zwei Feeds mit je 13 s Timeout (die Lektion aus #51).

**Alles zusammen als *eine* System-Nachricht.** Vorher war jedes Item eine
eigene; bei 2 Feeds × 4 Items waren das neun System-Nachrichten ohne
Zeichenbudget in einem 8k-Fenster.
"""

from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

import requests
from bs4 import BeautifulSoup
from config.config_singleton import Config
from core.context_injection import injected_message
from security.tinyguard import accepted_context


def _local(tag: str) -> str:
    # Atom-Tags kommen namespaced ("{http://…}title"), RSS 2.0 nackt.
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        for child in element:
            if _local(child.tag) == name and child.text:
                return child.text
    return ""


def _strip_html(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


@dataclass(frozen=True)
class RssItem:
    """Eine Meldung — **mit Datum**, das ist der Unterschied zu vorher (#73).

    ``_parse_feed`` las bisher nur Titel und Text. Ohne Datum kann das Modell
    nicht wissen, ob eine Meldung von heute oder von vorgestern ist — und sagt
    dann „heute" über Vorgestern. Für eine Nachrichtenquelle ist das der
    Unterschied zwischen Quelle und Gerücht.
    """

    source: str
    title: str
    body: str
    published: datetime | None = None

    def as_line(self, max_chars: int) -> str:
        stamp = self.published.strftime("%d.%m. %H:%M") if self.published else "?"
        text = " ".join(part for part in (self.title, self.body) if part).strip()
        if max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars].rstrip() + " […]"
        return f"[{self.source}, {stamp}] {text}"


def _parse_date(value: str) -> datetime | None:
    """RSS liefert RFC-822, Atom ISO-8601 — beides ohne Drama."""
    text = (value or "").strip()
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_feed(xml_text: str, source: str, max_items: int) -> list[RssItem]:
    """Liest RSS 2.0 (`channel/item`) und Atom (`entry`); kaputtes XML → ValueError."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid feed XML: {exc}") from exc

    entries = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    items: list[RssItem] = []
    for entry in entries[: max(0, max_items)]:
        title = _strip_html(_child_text(entry, ("title",)))
        body = _strip_html(_child_text(entry, ("description", "summary", "content")))
        published = _parse_date(
            _child_text(entry, ("pubDate", "published", "updated", "date"))
        )
        if title or body:
            items.append(
                RssItem(source=source, title=title, body=body, published=published)
            )
    return items


def fetch_feed_items(feed: dict, max_items: int, timeout: tuple[float, float]):
    """Ein Feed, einmal geholt. Fehler sind hier normal, nicht aussergewoehnlich."""
    name = str(feed.get("name") or feed.get("url") or "").strip()
    url = str(feed.get("url") or "").strip()
    if not url:
        return name, [], "no url configured"
    try:
        response = requests.get(
            url, timeout=timeout, headers={"User-Agent": "YulYenRSS/1.0"}
        )
        response.raise_for_status()
        return name, _parse_feed(response.text, name, max_items), None
    except (requests.exceptions.RequestException, ValueError) as err:
        logging.error("[RSS] Feed '%s' fehlgeschlagen: %s", name, err)
        return name, [], str(err)


@dataclass
class RssCache:
    """Die neuesten Meldungen je Quelle — im Speicher, im Hintergrund geholt.

    **Kein Archiv.** Der Cache *ist* der ganze Zustand: keine Migration, keine
    Retention, nichts, was über Wochen anwächst. Wer Nachrichten von letzter
    Woche sucht, ist beim Wiki besser aufgehoben.

    **Und kein Lazy-Load.** ``items_for`` holt nie selbst; es liefert, was der
    Hintergrund-Thread zuletzt geholt hat. Sonst zahlt genau die Frage, die
    nach Ablauf der Frist zuerst kommt, die volle Netz-Latenz — und das ist
    dieselbe Falle, die #51 vier Sekunden gekostet hat.
    """

    feeds: list[dict] = field(default_factory=list)
    max_items_per_feed: int = 4
    max_chars_per_item: int = 400
    refresh_minutes: int = 60
    timeout: tuple[float, float] = (5.0, 8.0)

    _items: dict[str, list[RssItem]] = field(default_factory=dict, repr=False)
    _failed: dict[str, str] = field(default_factory=dict, repr=False)
    _filled_at: float | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    @property
    def feed_names(self) -> list[str]:
        return [
            str(feed.get("name") or feed.get("url") or "").strip()
            for feed in self.feeds
            if (feed.get("name") or feed.get("url"))
        ]

    @property
    def filled_at(self) -> datetime | None:
        """Wann der Cache zuletzt gefüllt wurde — gehört an den Kontext-Block."""
        if self._filled_at is None:
            return None
        return datetime.fromtimestamp(self._filled_at)

    def refresh(self) -> None:
        """Alle Feeds einmal holen. Blockiert — gehört in den Hintergrund."""
        items: dict[str, list[RssItem]] = {}
        failed: dict[str, str] = {}
        for feed in self.feeds:
            name, feed_items, error = fetch_feed_items(
                feed, self.max_items_per_feed, self.timeout
            )
            if not name:
                continue
            if error:
                failed[name] = error
                continue
            items[name] = feed_items
        with self._lock:
            # Ein gescheiterter Feed wirft seinen letzten guten Stand nicht weg:
            # eine Minute Netzausfall soll nicht die Meldungen von vorhin löschen.
            self._items.update(items)
            self._failed = failed
            self._filled_at = time.time()

    def items_for(self, names: list[str]) -> list[RssItem]:
        with self._lock:
            return [item for name in names for item in self._items.get(name, [])]

    def failed_feeds(self) -> dict[str, str]:
        with self._lock:
            return dict(self._failed)

    def start(self) -> threading.Thread | None:
        """Startet den Auffrisch-Thread; erster Lauf sofort, dann im Takt."""
        if not self.feeds:
            return None

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.refresh()
                except Exception:
                    logging.exception("[RSS] Auffrischen fehlgeschlagen.")
                self._stop.wait(max(60, self.refresh_minutes * 60))

        thread = threading.Thread(target=_loop, name="RssCache", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stop.set()


def build_context_block(items: list[RssItem], cache: RssCache, guard: Any = None):
    """Alle Meldungen als **ein** Textblock — oder ``None``.

    Der Guard filtert **pro Meldung, bevor zusammengefügt wird**. Andersherum
    wäre die Zusammenfassung eine stille Abschwächung: eine einzige schräge
    Schlagzeile risse entweder den ganzen Block mit oder rutschte in ihm durch.
    Genau derselbe Fehler wie damals bei ``WikiLookup.snippets()``, nur
    andersherum.
    """
    accepted = accepted_context(
        guard,
        items,
        text_of=lambda item: f"{item.title} {item.body}",
        label_of=lambda item: item.source,
    )
    if not accepted:
        return None, len(items)
    cfg = Config()
    stamp = cache.filled_at.strftime("%H:%M") if cache.filled_at else "?"
    lines = "\n".join(item.as_line(cache.max_chars_per_item) for item in accepted)
    block = cfg.t("rss_context_block", stand=stamp, meldungen=lines)
    return block, len(items) - len(accepted)


def inject_rss_context(history: list, block: str | None) -> None:
    """Hängt Guardrail + **einen** zitierten Meldungsblock an die History.

    Wie beim Wiki (#60): die Anweisung bleibt ``system``, die Meldungen werden
    zitierter ``user``-Fremdtext. Eine Schlagzeile ist Material, kein Befehl —
    und ein Feed ist genau der Kanal, den man am leichtesten fremdbefüllt.
    """
    if not block:
        return
    cfg = Config()
    history.append({"role": "system", "content": cfg.t("rss_context_guardrail")})
    history.append(injected_message(cfg.t("context_quote_wrapper", body=block), "rss"))


def build_rss_cache(rss_cfg: dict | None) -> RssCache:
    """Baut den Cache aus der ``rss``-Sektion; ausgeschaltet = leerer Cache.

    Ein leerer Cache ist bewusst kein ``None``: die Oberflächen fragen ihn ohne
    Fallunterscheidung, und ``feed_names`` ist dann eben leer — womit die
    Heuristik nie auslöst und der Knopf verschwindet.
    """
    cfg = rss_cfg or {}
    if not cfg.get("enabled", False):
        return RssCache(feeds=[])
    return RssCache(
        feeds=list(cfg.get("feeds") or []),
        max_items_per_feed=int(cfg.get("max_items_per_feed", 4)),
        max_chars_per_item=int(cfg.get("max_chars_per_item", 400)),
        refresh_minutes=int(cfg.get("refresh_minutes", 60)),
        timeout=(
            float(cfg.get("timeout_connect", 5.0)),
            float(cfg.get("timeout_read", 8.0)),
        ),
    )


def _rss_cache_of(factory) -> RssCache:
    """Der Cache der Factory — oder ein leerer, wenn keine da ist.

    Die Oberflächen werden in Tests auch ohne Factory gebaut; ein leerer Cache
    verhält sich dann wie eine abgeschaltete Quelle, statt beim Import zu
    scheitern.
    """
    getter = getattr(factory, "get_rss_cache", None)
    if callable(getter):
        return getter()
    return RssCache(feeds=[])
