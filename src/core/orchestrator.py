"""Utilities to fan out a prompt across the full persona ensemble."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Iterable, Iterator

from config.personas import get_all_persona_names

from core.streaming_provider import YulYenStreamingProvider


def iter_broadcast_events(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    *,
    context_messages: Iterable[dict[str, str]] | None = None,
) -> Iterator[dict[str, str]]:
    """Runs the same prompt sequentially for every persona, yielding per token.

    Lowest-level broadcast primitive; the other broadcast helpers build on it.

    Args:
        factory: Object that can build a :class:`YulYenStreamingProvider` via
            ``get_streamer_for_persona``.
        user_input: Prompt to send to every persona.
        persona_names: Optional custom subset. Defaults to all personas in the
            active ensemble.
        context_messages: Optional messages (e.g. injected wiki snippets)
            placed before the user prompt for every persona.

    Yields:
        ``{"type": "token", "persona": ..., "token": ...}`` for every streamed
        token and ``{"type": "done", "persona": ..., "reply": ...}`` once a
        persona has finished (``reply`` is the full, stripped text).

    Ein Token-Event trägt **nur** sein Token, nicht den Text bis hierhin
    (#64d): der kumulative String wurde bei jedem Token neu gebaut und in das
    Event gelegt — quadratisch in der Antwortlänge, und weil jedes Event seine
    eigene Kopie festhält, auch im Speicher. Wer den laufenden Text braucht,
    sammelt die Token in einer Liste und fügt sie zusammen, wenn er sie zeigt;
    das tut die WebUI beim Auffrischen der Anzeige.
    """

    personas = (
        list(persona_names) if persona_names is not None else get_all_persona_names()
    )
    base_messages = list(context_messages or [])

    for persona in personas:
        streamer: YulYenStreamingProvider = factory.get_streamer_for_persona(persona)
        # Jede Persona bekommt ihr eigenes Gespräch in der Ablage (#59). Vorher
        # wurde hier nie eine Gesprächs-ID gesetzt, weshalb der ganze
        # Broadcast-Modus spurlos blieb — obwohl er dieselben Fragen und
        # Antworten erzeugt wie ein Einzelchat.
        messages = base_messages + [{"role": "user", "content": user_input}]
        _open_conversation_for(factory, streamer, persona)
        reply_so_far = ""

        parts: list[str] = []
        for token in streamer.stream(messages=messages):
            parts.append(token)
            yield {"type": "token", "persona": persona, "token": token}

        reply_so_far = "".join(parts)
        _record(streamer, messages, reply_so_far)
        yield {"type": "done", "persona": persona, "reply": reply_so_far.strip()}


def _open_conversation_for(factory, streamer, persona: str) -> None:
    """Eröffnet ein Gespräch für diese Persona — best effort.

    Der Broadcast lief bisher ohne Gesprächs-ID; ``append``/``sync`` steigen bei
    leerer ID aus, also zeichnete Ask-All nichts auf. Fehlschläge dürfen den
    Broadcast nicht anhalten, deshalb schluckt ``open_conversation`` sie bereits.
    """
    opener = getattr(factory, "open_conversation", None)
    setter = getattr(streamer, "set_conversation", None)
    if callable(opener) and callable(setter):
        setter(opener(persona, "ask-all"))


def _record(streamer, messages: list[dict[str, str]], reply: str) -> None:
    """Gesprächsstand in die Ablage spiegeln, sobald die Antwort feststeht."""
    recorder = getattr(streamer, "record_conversation", None)
    if callable(recorder):
        recorder([*messages, {"role": "assistant", "content": reply.strip()}])


def iter_broadcast_events_parallel(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    *,
    context_messages: Iterable[dict[str, str]] | None = None,
    stop_event: threading.Event | None = None,
    join_timeout_s: float = 5.0,
) -> Iterator[dict[str, str]]:
    """Like :func:`iter_broadcast_events`, but all personas stream concurrently.

    Event format is identical; token events of different personas interleave.
    Closing the generator signals every worker to stop and closes its LLM
    stream.

    Args:
        stop_event: Optional external kill switch. Needed for Gradio cancels:
            das bricht nur den asyncio-Task ab und schließt den Generator
            nicht — der Aufrufer muss das Event selbst setzen können.
        join_timeout_s: Grace period per worker thread on shutdown; a worker
            stuck in a blocking backend read is logged and abandoned (daemon).
    """

    personas = (
        list(persona_names) if persona_names is not None else get_all_persona_names()
    )
    base_messages = list(context_messages or [])

    # Build streamers up front: the factory reads the config singleton and is
    # not guaranteed to be thread-safe.
    streamers = {name: factory.get_streamer_for_persona(name) for name in personas}

    events: queue.Queue[dict[str, str]] = queue.Queue()
    stop = stop_event if stop_event is not None else threading.Event()

    def _worker(persona: str, streamer: YulYenStreamingProvider) -> None:
        parts: list[str] = []
        messages = base_messages + [{"role": "user", "content": user_input}]
        _open_conversation_for(factory, streamer, persona)
        token_stream = streamer.stream(messages=messages)
        try:
            for token in token_stream:
                if stop.is_set():
                    break
                parts.append(token)
                events.put({"type": "token", "persona": persona, "token": token})
        finally:
            reply_so_far = "".join(parts)
            # Triggers the provider's finally → closes the backend stream.
            token_stream.close()
            # Auch eine abgebrochene Antwort ist das, was der Nutzer gesehen
            # hat — sie gehört so in die Ablage (#59).
            _record(streamer, messages, reply_so_far)
            events.put(
                {"type": "done", "persona": persona, "reply": reply_so_far.strip()}
            )

    threads = [
        threading.Thread(
            target=_worker,
            args=(name, streamer),
            daemon=True,
            name=f"broadcast-{name}",
        )
        for name, streamer in streamers.items()
    ]
    for thread in threads:
        thread.start()

    pending = len(threads)
    try:
        while pending:
            event = events.get()
            if event["type"] == "done":
                pending -= 1
            yield event
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=join_timeout_s)
            if thread.is_alive():
                logging.warning(
                    "Broadcast worker %s did not stop within %ss",
                    thread.name,
                    join_timeout_s,
                )


def iter_broadcast(
    factory,
    user_input: str,
    persona_names: Iterable[str] | None = None,
    on_token: Callable[[str, str], None] | None = None,
    *,
    context_messages: Iterable[dict[str, str]] | None = None,
) -> Iterator[dict[str, str]]:
    """Like :func:`iter_broadcast_events`, but yields once per finished persona.

    ``on_token`` optionally receives ``(persona, token)`` for streaming
    progress reporting.
    """

    for event in iter_broadcast_events(
        factory, user_input, persona_names, context_messages=context_messages
    ):
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
    *,
    context_messages: Iterable[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Like :func:`iter_broadcast`, but collects all results into a list."""

    return list(
        iter_broadcast(
            factory,
            user_input,
            persona_names,
            on_token,
            context_messages=context_messages,
        )
    )
