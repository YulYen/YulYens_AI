"""Utilities to fan out a prompt across the full persona ensemble."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from config.personas import get_all_persona_names

from core.streaming_provider import YulYenStreamingProvider


def iter_broadcast_events(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
) -> Iterator[dict[str, str]]:
    """Runs the same prompt sequentially for every persona, yielding per token.

    Lowest-level broadcast primitive; the other broadcast helpers build on it.

    Args:
        factory: Object that can build a :class:`YulYenStreamingProvider` via
            ``get_streamer_for_persona``.
        user_input: Prompt to send to every persona.
        persona_names: Optional custom subset. Defaults to all personas in the
            active ensemble.

    Yields:
        ``{"type": "token", "persona": ..., "token": ..., "reply": ...}`` for
        every streamed token (``reply`` is the cumulative text so far) and
        ``{"type": "done", "persona": ..., "reply": ...}`` once a persona has
        finished (``reply`` is the full, stripped text).
    """

    personas = (
        list(persona_names) if persona_names is not None else get_all_persona_names()
    )

    for persona in personas:
        streamer: YulYenStreamingProvider = factory.get_streamer_for_persona(persona)
        reply_so_far = ""

        for token in streamer.stream(
            messages=[{"role": "user", "content": user_input}]
        ):
            reply_so_far += token
            yield {
                "type": "token",
                "persona": persona,
                "token": token,
                "reply": reply_so_far,
            }

        yield {"type": "done", "persona": persona, "reply": reply_so_far.strip()}


def iter_broadcast(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    on_token: Callable[[str, str], None] | None = None,
) -> Iterator[dict[str, str]]:
    """Like :func:`iter_broadcast_events`, but yields once per finished persona.

    ``on_token`` optionally receives ``(persona, token)`` for streaming
    progress reporting.
    """

    for event in iter_broadcast_events(factory, user_input, persona_names):
        if event["type"] == "token":
            if on_token:
                on_token(event["persona"], event["token"])
        else:
            yield {"persona": event["persona"], "reply": event["reply"]}


def broadcast_to_ensemble(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    on_token: Callable[[str, str], None] | None = None,
) -> list[dict[str, str]]:
    """Like :func:`iter_broadcast`, but collects all results into a list."""

    return list(iter_broadcast(factory, user_input, persona_names, on_token))
