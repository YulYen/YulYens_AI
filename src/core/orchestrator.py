"""Utilities to fan out a prompt across the full persona ensemble."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

from config.personas import get_all_persona_names

from core.streaming_provider import YulYenStreamingProvider


def iter_broadcast(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    on_token: Callable[[str, str], None] | None = None,
) -> Iterator[dict[str, str]]:
    """Runs the same prompt sequentially for every persona, yielding per persona.

    Args:
        factory: Object that can build a :class:`YulYenStreamingProvider` via
            ``get_streamer_for_persona``.
        user_input: Prompt to send to every persona.
        persona_names: Optional custom subset. Defaults to all personas in the
            active ensemble.
        on_token: Optional callback that receives ``(persona, token)`` for
            streaming progress reporting.

    Yields:
        One dictionary per persona with the persona name and the collected
        reply text, as soon as that persona has finished.
    """

    personas = (
        list(persona_names) if persona_names is not None else get_all_persona_names()
    )

    for persona in personas:
        streamer: YulYenStreamingProvider = factory.get_streamer_for_persona(persona)
        reply_parts: list[str] = []

        for token in streamer.stream(
            messages=[{"role": "user", "content": user_input}]
        ):
            reply_parts.append(token)
            if on_token:
                on_token(persona, token)

        yield {"persona": persona, "reply": "".join(reply_parts).strip()}


def broadcast_to_ensemble(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    on_token: Callable[[str, str], None] | None = None,
) -> list[dict[str, str]]:
    """Like :func:`iter_broadcast`, but collects all results into a list."""

    return list(iter_broadcast(factory, user_input, persona_names, on_token))
