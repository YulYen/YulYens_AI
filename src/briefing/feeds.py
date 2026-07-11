"""RSS/Atom-Briefing: Feeds holen und als Kontext für die Personas injizieren.

Spiegelt bewusst die Wiki-Pipeline (wiki/lookup.py): fetch liefert
(UI-Hints, Items), inject hängt Guardrail + System-Messages an die History.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup
from config.config_singleton import Config


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


def _parse_feed(xml_text: str, max_items: int) -> list[tuple[str, str]]:
    """Liest RSS 2.0 (`channel/item`) und Atom (`entry`); kaputtes XML → ValueError."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid feed XML: {exc}") from exc

    entries = [el for el in root.iter() if _local(el.tag) in ("item", "entry")]
    items: list[tuple[str, str]] = []
    for entry in entries[: max(0, max_items)]:
        title = _strip_html(_child_text(entry, ("title",)))
        body = _strip_html(_child_text(entry, ("description", "summary", "content")))
        if title or body:
            items.append((title, body))
    return items


def fetch_briefing_items(
    briefing_cfg: dict,
    persona_name: str,
    timeout: tuple[float, float],
) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Holt die konfigurierten Feeds. Liefert UI-Hints und (Quelle, Text)-Paare
    für die Kontext-Injektion; nicht erreichbare Feeds werden übersprungen.
    """
    cfg = Config()
    hints: list[str] = []
    items: list[tuple[str, str]] = []
    max_items = int(briefing_cfg.get("max_items_per_feed", 4))

    for feed in briefing_cfg.get("feeds") or []:
        feed_name = str(feed.get("name") or feed.get("url") or "").strip()
        url = str(feed.get("url") or "").strip()
        if not url:
            continue
        try:
            response = requests.get(
                url, timeout=timeout, headers={"User-Agent": "YulYenBriefing/1.0"}
            )
            response.raise_for_status()
            feed_items = _parse_feed(response.text, max_items)
        except (requests.exceptions.RequestException, ValueError) as err:
            logging.error("[BRIEFING EXC] Feed '%s' fehlgeschlagen: %s", feed_name, err)
            hints.append(cfg.t("briefing_hint_failed", feed_name=feed_name))
            continue

        hints.append(
            cfg.t("briefing_hint", persona_name=persona_name, feed_name=feed_name)
        )
        for title, body in feed_items:
            items.append((f"{feed_name}: {title}" if title else feed_name, body))
    return (hints, items)


def inject_briefing_context(history: list, items: list[tuple[str, str]]) -> None:
    """
    Hängt wie inject_wiki_context eine Guardrail-Message und eine
    System-Message pro Meldung an die History an (mutiert in place).
    """
    if not items:
        return
    cfg = Config()
    history.append({"role": "system", "content": cfg.t("briefing_context_guardrail")})

    for idx, (source, snippet) in enumerate(items, start=1):
        context_message = cfg.t(
            "briefing_context_message", source=source, snippet=snippet
        )
        history.append(
            {
                "role": "system",
                "content": f"=== BRIEFING {idx}: {source} ===\n{context_message}",
            }
        )
