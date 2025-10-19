"""Deterministische LLM‑Core‑Implementierung für schnelle Tests.

Diese Klasse implementiert das :class:`LLMCore`‑Interface und antwortet
deterministisch mit einem einfachen Echo. Sie ist nützlich für Unit‑Tests,
bei denen kein echtes LLM benötigt wird.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .llm_core import LLMCore


class DummyLLMCore(LLMCore):
    """Eine LLM‑Core‑Implementierung, die einfach den User‑Input zurückgibt."""

    def warm_up(self, model_name: str) -> None:
        """Kein Vorheizen erforderlich für den Dummy."""
        return None

    def stream_chat(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        options: Dict[str, Any] | None = None,
        keep_alive: int = 600,
    ) -> Iterable[Dict[str, Any]]:
        """
        Gibt genau einen Antwort‑Chunk zurück, der den User‑Input spiegelt.

        :param model_name: Wird ignoriert.
        :param messages: Liste der Nachrichten; die letzte Nutzer‑Nachricht wird gespiegelt.
        :param options: Ignoriert.
        :param keep_alive: Ignoriert.
        :returns: Iterator mit genau einem Element.
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
