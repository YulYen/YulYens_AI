from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from config.config_singleton import Config
from config.personas import get_all_persona_names
from wiki.lookup import inject_wiki_context, lookup_wiki_snippet


class UnknownPersonaError(ValueError):
    """Raised when an unknown persona is requested."""

    pass


class AiApiProvider:
    """Provides AI answers through the API (one-shot)."""

    def __init__(
        self,
        *,
        keyword_finder: Any,
        wiki_mode: str | bool,
        wiki_proxy_port: int,
        wiki_snippet_limit: int,
        max_wiki_snippets: int,
        wiki_timeout: tuple[float, float],
        factory: Any,
    ) -> None:
        self.keyword_finder = keyword_finder
        self.wiki_mode = wiki_mode
        self.wiki_proxy_port = wiki_proxy_port
        self.wiki_snippet_limit = wiki_snippet_limit
        self.max_wiki_snippets = max_wiki_snippets
        self.wiki_timeout = wiki_timeout
        self.factory = factory
        self.cfg = factory.get_config() if factory is not None else Config()
        self._known_personas = tuple(get_all_persona_names())
        self._persona_lookup = {name.lower(): name for name in self._known_personas}

    def known_personas(self) -> tuple[str, ...]:
        return self._known_personas

    def resolve_persona(self, persona: str) -> str:
        """Canonical persona name, case-insensitive. Raises on unknown names."""
        persona_key = (persona or "").strip().lower()
        if persona_key not in self._persona_lookup:
            known = ", ".join(self._known_personas)
            raise UnknownPersonaError(
                f"Unknown persona '{(persona or '').strip()}'. "
                f"Available personas: {known}."
            )
        return self._persona_lookup[persona_key]

    def stream_messages(
        self, messages: list[dict[str, Any]], persona: str
    ) -> Iterator[str]:
        """Token stream for a client-supplied history (OpenAI semantics, #37).

        The history is passed through as the client sent it — no Karl, no
        heuristic trimming: an OpenAI client owns its context window. Guard,
        wiki injection and conversation logging come along because they live in
        the streamer, which is the same one the UI uses.
        """
        canonical_persona = self.resolve_persona(persona)
        history = [dict(m) for m in messages or []]

        last_user_index = next(
            (
                i
                for i in range(len(history) - 1, -1, -1)
                if history[i].get("role") == "user"
            ),
            None,
        )
        if last_user_index is not None:
            question = str(history[last_user_index].get("content") or "")
            _hints, contexts = lookup_wiki_snippet(
                question,
                canonical_persona,
                self.keyword_finder,
                self.wiki_mode,
                self.wiki_proxy_port,
                self.wiki_snippet_limit,
                self.wiki_timeout,
                self.max_wiki_snippets,
            )
            if contexts:
                # Wie im UI: die Kontext-System-Messages stehen unmittelbar vor
                # dem User-Turn, auf den sie sich beziehen.
                tail = history[last_user_index:]
                del history[last_user_index:]
                inject_wiki_context(history, contexts)
                history.extend(tail)

        streamer = self.factory.get_streamer_for_persona(canonical_persona)
        yield from streamer.stream(messages=history)

    def answer(self, question: str, persona: str) -> str:
        """Handles a question for the given persona and returns the answer as text."""

        frage = (question or "").strip()

        if len(frage) == 0:
            return self.cfg.texts["empty_question"]

        canonical_persona = self.resolve_persona(persona)

        streamer = self.factory.get_streamer_for_persona(canonical_persona)

        return streamer.respond_one_shot(
            frage,
            keyword_finder=self.keyword_finder,
            wiki_mode=self.wiki_mode,
            wiki_proxy_port=self.wiki_proxy_port,
            wiki_snippet_limit=self.wiki_snippet_limit,
            wiki_timeout=self.wiki_timeout,
            max_wiki_snippets=self.max_wiki_snippets,
            persona=canonical_persona,
        ).strip()
