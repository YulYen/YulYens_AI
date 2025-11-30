"""Utilities to fan out a prompt across the full persona ensemble."""

from __future__ import annotations

from typing import Callable, Iterable

from config.personas import get_all_persona_names
from core.streaming_provider import YulYenStreamingProvider


def broadcast_to_ensemble(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    on_token: Callable[[str, str], None] | None = None,
) -> list[dict[str, str]]:
    """Runs the same prompt sequentially for every persona.

    Args:
        factory: Object that can build a :class:`YulYenStreamingProvider` via
            ``get_streamer_for_persona``.
        user_input: Prompt to send to every persona.
        persona_names: Optional custom subset. Defaults to all personas in the
            active ensemble.
        on_token: Optional callback that receives ``(persona, token)`` for
            streaming progress reporting.

    Returns:
        A list of dictionaries containing the persona name and the collected
        reply text.
    """

    personas = list(persona_names) if persona_names is not None else get_all_persona_names()
    results: list[dict[str, str]] = []

    for persona in personas:
        streamer: YulYenStreamingProvider = factory.get_streamer_for_persona(persona)
        reply_parts: list[str] = []

        for token in streamer.stream(messages=[{"role": "user", "content": user_input}]):
            reply_parts.append(token)
            if on_token:
                on_token(persona, token)

        results.append({"persona": persona, "reply": "".join(reply_parts).strip()})

    return results
