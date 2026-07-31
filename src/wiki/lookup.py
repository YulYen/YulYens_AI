"""Wiki snippet lookup via the local proxy and context injection for the LLM."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from config.config_singleton import Config


@dataclass(frozen=True)
class WikiSnippet:
    """Ein injizierter Wikipedia-Ausschnitt samt Herkunft (#32).

    ``snippet`` ist exakt der Text, der im Prompt landet — nicht der Artikel.
    ``full_length`` ist die Länge *vor* dem Kürzen; nur damit lässt sich
    anzeigen, dass das Modell den Rest des Artikels nie gesehen hat.
    """

    topic: str
    snippet: str
    link: str = ""
    source: str = ""
    full_length: int = 0

    @property
    def truncated(self) -> bool:
        return self.full_length > len(self.snippet)


def format_snippet_meta(snippet: WikiSnippet, t) -> str:
    """„Offline-Archiv · 1200 von 9800 Zeichen injiziert (gekürzt)" (#32a).

    Geteilt von WebUI und Terminal, damit die Auswahl der Locale-Keys
    (online/offline × gekürzt/vollständig) nur an einer Stelle steht und in
    beiden Oberflächen wortgleich dasselbe erscheint. ``t`` ist der
    Text-Formatter der Config.
    """
    origin = t(
        "wiki_source_online" if snippet.source == "online" else "wiki_source_local"
    )
    key = (
        "wiki_sources_meta_truncated" if snippet.truncated else "wiki_sources_meta_full"
    )
    return t(
        key,
        source=origin,
        shown=len(snippet.snippet),
        total=snippet.full_length,
    )


@dataclass(frozen=True)
class WikiLookup:
    """Die Wiki-Einstellungen als *ein* Ding statt als fünf lose Attribute.

    ``lookup_wiki_snippet`` wurde an sechs Stellen mit denselben acht
    Argumenten gerufen, und WebUI, TerminalUI und der API-Provider hielten je
    dieselben fünf ``wiki_*``-Attribute — eine neue Option hätte man an allen
    dreien nachziehen müssen. Die Factory baut das Objekt einmal und reicht es
    weiter.
    """

    keyword_finder: Any = None
    mode: str | bool = False
    proxy_port: int = 8042
    limit: int = 1200
    max_snippets: int = 2
    timeout: tuple[float, float] = (3.0, 8.0)

    @classmethod
    def from_config(cls, cfg, keyword_finder) -> WikiLookup:
        wiki = getattr(cfg, "wiki", {}) or {}
        return cls(
            keyword_finder=keyword_finder,
            mode=wiki.get("mode", False),
            proxy_port=int(wiki.get("proxy_port", 8042)),
            limit=int(wiki.get("snippet_limit", 1200)),
            max_snippets=int(wiki.get("max_wiki_snippets", 2)),
            timeout=(
                float(wiki.get("timeout_connect", 3.0)),
                float(wiki.get("timeout_read", 8.0)),
            ),
        )

    def snippets(
        self, question: str, persona_name: str
    ) -> tuple[list[str], list[WikiSnippet]]:
        """UI-Hinweise und Snippets zur Frage — leer, wenn Wiki aus ist."""
        return lookup_wiki_snippet(
            question,
            persona_name,
            self.keyword_finder,
            self.mode,
            self.proxy_port,
            self.limit,
            self.timeout,
            self.max_snippets,
        )


def lookup_wiki_snippet(
    question: str,
    persona_name: str,
    keyword_finder,
    wiki_mode: str | bool,
    proxy_port: int,
    limit: int,
    timeout: tuple[float, float],
    max_snippets: int,
) -> tuple[list[str], list[WikiSnippet]]:
    """
    Helper function: fetches up to ``max_snippets`` Wikipedia snippets via a local proxy.
    Returns UI hints (only when snippets are found) and ``WikiSnippet`` objects for
    context injection.
    """
    wiki_hints: list[str] = []
    contexts: list[WikiSnippet] = []
    proxy_base = "http://localhost:" + str(proxy_port)

    if not keyword_finder or max_snippets <= 0:
        return (wiki_hints, contexts)

    topics = keyword_finder.find_keywords(question)

    for topic in topics[:max_snippets]:
        if len(contexts) >= max_snippets:
            break
        if not topic:
            continue

        online_flag = "1" if wiki_mode == "online" else "0"
        encoded_topic = quote(topic, safe="")
        url = (
            f"{proxy_base.rstrip('/')}/{encoded_topic}"
            f"?json=1&limit={limit}&online={online_flag}&persona={persona_name}"
        )
        try:
            proxy_response = requests.get(url, timeout=timeout)

            if proxy_response.status_code == 200:
                data = proxy_response.json()
                text = (data.get("text") or "").replace("\r", " ").strip()
                snippet = text[:limit]
                wiki_hint = data.get("wiki_hint")
                topic_title = (data.get("title") or topic).replace("_", " ")

                if wiki_hint:
                    wiki_hints.append(wiki_hint)
                if snippet:
                    contexts.append(
                        WikiSnippet(
                            topic=topic_title,
                            snippet=snippet,
                            link=str(data.get("link") or ""),
                            source=str(data.get("source") or ""),
                            full_length=_full_length(data, snippet),
                        )
                    )
            elif proxy_response.status_code == 404:
                logging.info("[WIKI] No entry found for topic '%s'", topic)
            else:
                logging.warning(
                    "[WIKI] Unexpected status %s for topic '%s'",
                    proxy_response.status_code,
                    topic,
                )
        except requests.exceptions.RequestException as err:
            logging.error(
                "[WIKI EXC] Network error while retrieving '%s': %s",
                topic,
                err,
                exc_info=True,
            )
        except Exception:  # pragma: no cover - unexpected errors
            logging.exception("[WIKI EXC] Unexpected error for topic='%s'", topic)
    return (wiki_hints, contexts)


def _full_length(data: dict, snippet: str) -> int:
    """Originallänge des Artikeltexts laut Proxy, sonst die des Snippets.

    Gekürzt wird bereits im Proxy, deshalb liefert der die Länge vorher separat
    mit. Fehlt das Feld (alter Proxy, Testdouble), ist der Snippet das Beste,
    was wir wissen — dann gilt er als vollständig statt fälschlich als gekürzt.
    """
    try:
        reported = int(data.get("full_length") or 0)
    except (TypeError, ValueError):
        reported = 0
    return max(reported, len(snippet))


def inject_wiki_context(history: list, contexts: list[WikiSnippet]) -> None:
    """
    If Wikipedia snippets are available, append a guardrail message and one
    system message per snippet. Each snippet block is clearly delimited.
    """
    if not contexts:
        return
    cfg = Config()
    guardrail = cfg.t("wiki_context_guardrail")
    history.append({"role": "system", "content": guardrail})

    for idx, ctx in enumerate(contexts, start=1):
        topic_clean = ctx.topic.replace("_", " ")
        context_message = cfg.t(
            "wiki_context_message", topic=topic_clean, snippet=ctx.snippet
        )
        formatted_context = (
            f"=== WIKI SNIPPET {idx}: {topic_clean} ===\n{context_message}"
        )
        history.append({"role": "system", "content": formatted_context})
