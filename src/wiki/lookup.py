"""Wiki snippet lookup via the local proxy and context injection for the LLM."""

from __future__ import annotations

import logging
from urllib.parse import quote

import requests
from config.config_singleton import Config


def lookup_wiki_snippet(
    question: str,
    persona_name: str,
    keyword_finder,
    wiki_mode: str,
    proxy_port: int,
    limit: int,
    timeout: tuple[float, float],
    max_snippets: int,
) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Helper function: fetches up to ``max_snippets`` Wikipedia snippets via a local proxy.
    Returns UI hints (only when snippets are found) and (topic, snippet) pairs for
    context injection.
    """
    wiki_hints: list[str] = []
    contexts: list[tuple[str, str]] = []
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
                    contexts.append((topic_title, snippet))
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


def inject_wiki_context(history: list, contexts: list[tuple[str, str]]) -> None:
    """
    If Wikipedia snippets are available, append a guardrail message and one
    system message per snippet. Each snippet block is clearly delimited.
    """
    if not contexts:
        return
    cfg = Config()
    guardrail = cfg.t("wiki_context_guardrail")
    history.append({"role": "system", "content": guardrail})

    for idx, (topic, snippet) in enumerate(contexts, start=1):
        topic_clean = topic.replace("_", " ")
        context_message = cfg.t(
            "wiki_context_message", topic=topic_clean, snippet=snippet
        )
        formatted_context = (
            f"=== WIKI SNIPPET {idx}: {topic_clean} ===\n{context_message}"
        )
        history.append({"role": "system", "content": formatted_context})
