"""Thin wrapper around the Ollama client."""

from __future__ import annotations

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

    def warm_up(self, model_name: str) -> None:
        """
        Performs a dummy call to preload the model.

        :param model_name: Name of the model to warm up
        """
        self._client.chat(
            model=model_name, messages=[{"role": "user", "content": "..."}]
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
        )
