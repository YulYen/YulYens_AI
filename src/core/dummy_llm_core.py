"""Deterministic LLM core implementation for quick tests.

This class implements the :class:`LLMCore` interface and responds
deterministically with a simple echo. It is useful for unit tests where
no real LLM is required.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .llm_core import LLMCore


class DummyLLMCore(LLMCore):
    """An LLM core implementation that simply returns the user input."""

    def warm_up(self, model_name: str) -> None:
        """No warm-up required for the dummy."""
        return None

    def stream_chat(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        options: Dict[str, Any] | None = None,
        keep_alive: int = 600,
    ) -> Iterable[Dict[str, Any]]:
        """
        Returns exactly one response chunk that mirrors the user input.

        :param model_name: Ignored.
        :param messages: List of messages; mirrors the last user message.
        :param options: Ignored.
        :param keep_alive: Ignored.
        :returns: Iterator with exactly one element.
        """
        # Die letzte User‑Nachricht finden
        user_input = ""
        for m in reversed(messages or []):
            if m.get("role") == "user":
                user_input = m.get("content", "") or ""
                break
        response = f"ECHO: {user_input}"
        # Return a dictionary with message.content in Ollama style
        yield {"message": {"content": response}}
