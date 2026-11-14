"""Thin wrapper around the Ollama client.

Eine Regel wohnt hier: **ein Modell, das denken kann, denkt bei uns nicht**
(#78). Qwen 3.x und andere Reasoning-Modelle schicken ihre Überlegung in
`message.thinking` voraus; der Streamer liest nur `message.content`. Ohne
`think=False` bleibt die Antwort deshalb lange leer — die Stoppuhr mäße das
Nachdenken als Latenz, und der Judge bekäme es bezahlt, ohne es zu sehen.

Gefragt wird das Modell selbst (`show().capabilities`), nicht eine Namensliste:
ein Modell ohne die Fähigkeit bekommt den Parameter gar nicht erst, seine
Anfrage bleibt Byte für Byte die alte. Das ist Absicht — `think=True` weist
Ollama bei solchen Modellen ab, und ob jede Server-Fassung `think=False`
durchwinkt, ist hier nicht gemessen.
"""

from __future__ import annotations

import logging
from typing import Any

from ollama import Client

# LLM‑Interface importieren
from .llm_core import LLMCore


class OllamaLLMCore(LLMCore):
    """Minimal wrapper for the Ollama client."""

    def __init__(self, base_url: str) -> None:
        """
        Initializes the Ollama client.

        :param base_url: URL of the Ollama server (e.g. http://localhost:11434)
        """
        self._client = Client(host=base_url)
        self._can_think: dict[str, bool] = {}

    def _think_kwargs(self, model_name: str) -> dict[str, Any]:
        """`{"think": False}` für ein Modell, das denken kann, sonst nichts.

        Die Antwort wird je Modell gemerkt — aber nur eine *erhaltene*. Ist
        Ollama gerade nicht erreichbar, fragt der nächste Aufruf erneut, statt
        ein Reasoning-Modell für den Rest des Prozesses denken zu lassen.
        """
        can_think = self._can_think.get(model_name)
        if can_think is None:
            try:
                capabilities = self._client.show(model_name).capabilities or []
            except Exception as exc:  # die Nachfrage darf keinen Chat verhindern
                logging.debug(f"[OLLAMA] show({model_name!r}) failed: {exc}")
                return {}
            can_think = "thinking" in capabilities
            self._can_think[model_name] = can_think
        return {"think": False} if can_think else {}

    def warm_up(
        self,
        model_name: str,
        options: dict[str, Any] | None = None,
        keep_alive: int = 600,
    ) -> None:
        """
        Performs a dummy call to preload the model.

        :param model_name: Name of the model to warm up
        :param options: Generation options (num_ctx, …) so the model loads
            with the same KV-cache size as real requests
        :param keep_alive: Keep-alive timeout in seconds
        """
        self._client.chat(
            model=model_name,
            keep_alive=keep_alive,
            messages=[{"role": "user", "content": "..."}],
            options=options or {},
            **self._think_kwargs(model_name),
        )

    def stream_chat(
        self,
        model_name: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        keep_alive: int = 600,
    ):
        """
        Starts a streaming chat.

        :param model_name: Name of the model
        :param messages: List of messages (in Ollama format)
        :param options: Generation options (temperature, top_p, …)
        :param keep_alive: Keep-alive timeout
        :returns: Iterator over the response chunks
        """
        return self._client.chat(
            model=model_name,
            keep_alive=keep_alive,
            messages=messages,
            options=options or {},
            stream=True,
            **self._think_kwargs(model_name),
        )
