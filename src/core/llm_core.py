"""Abstract base class for all LLM cores.

This interface defines the minimal methods an LLM core must provide.
By using this base class, different implementations (e.g. for Ollama or
a dummy used in tests) can be swapped seamlessly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any


class LLMCore(ABC):
    """Interface for accessing a large language model."""

    @abstractmethod
    def warm_up(self, model_name: str) -> None:
        """
        Warms up the model so the first token is available faster.

        :param model_name: Name of the model to warm up
        """
        raise NotImplementedError

    @abstractmethod
    def stream_chat(
        self,
        model_name: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        keep_alive: int = 600,
    ) -> Iterable[dict[str, Any]]:
        """
        Starts a chat in streaming mode.

        :param model_name: Name of the model
        :param messages: List of messages (in the LLM format)
        :param options: Generation options (temperature, top_p, …)
        :param keep_alive: Keep-alive timeout in seconds
        :returns: Iterable over the model's response chunks
        """
        raise NotImplementedError
