from __future__ import annotations

"""
Dünner Wrapper um den Ollama‑Client.

Diese Klasse kapselt alle direkten Aufrufe an das Ollama‑Backend, sodass das
restliche System vom konkreten LLM entkoppelt ist. Sollte Ollama
ausgetauscht werden, muss nur diese Klasse angepasst werden.
"""

from typing import Any, Dict, List

# LLM‑Interface importieren
from .llm_core import LLMCore
from ollama import Client


class OllamaLLMCore(LLMCore):
    """Minimaler Wrapper für den Ollama‑Client."""

    def __init__(self, base_url: str) -> None:
        """
        Initialisiert den Ollama‑Client.

        :param base_url: URL des Ollama‑Servers (z. B. http://localhost:11434)
        """
        self._client = Client(host=base_url)

    def warm_up(self, model_name: str) -> None:
        """
        Führt einen Dummy‑Aufruf aus, um das Modell vorzuladen.

        :param model_name: Name des zu wärmenden Modells
        """
        self._client.chat(model=model_name, messages=[{"role": "user", "content": "..."}])

    def stream_chat(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        options: Dict[str, Any] | None = None,
        keep_alive: int = 600,
    ):
        """
        Startet einen Streaming‑Chat.

        :param model_name: Name des Modells
        :param messages: Liste der Nachrichten (im Ollama‑Format)
        :param options: Generierungsoptionen (temperature, top_p, …)
        :param keep_alive: Keep‑Alive‑Timeout
        :returns: Iterator über die Antwort‑Chunks
        """
        return self._client.chat(
            model=model_name,
            keep_alive=keep_alive,
            messages=messages,
            options=options or {},
            stream=True,
        )
