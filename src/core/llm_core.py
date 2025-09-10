
"""Abstrakte Basis-Klasse für alle LLM‑Kerne.

Dieses Interface definiert die minimalen Methoden, die ein LLM‑Core zur
Verfügung stellen muss. Durch die Verwendung dieser Basisklasse können
verschiedene Implementierungen (z. B. für Ollama oder einen Dummy für Tests)
austauschbar eingesetzt werden.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Iterable, List


class LLMCore(ABC):
    """Interface für den Zugriff auf ein Large Language Model."""

    @abstractmethod
    def warm_up(self, model_name: str) -> None:
        """
        Heizt das Modell vor, damit der erste Token schneller verfügbar ist.

        :param model_name: Name des zu wärmenden Modells
        """
        raise NotImplementedError

    @abstractmethod
    def stream_chat(
        self,
        model_name: str,
        messages: List[Dict[str, Any]],
        options: Dict[str, Any] | None = None,
        keep_alive: int = 600,
    ) -> Iterable[Dict[str, Any]]:
        """
        Startet einen Chat im Streaming‑Modus.

        :param model_name: Name des Modells
        :param messages: Liste der Nachrichten (im LLM‑Format)
        :param options: Generierungsoptionen (temperature, top_p, …)
        :param keep_alive: Keep‑Alive‑Timeout in Sekunden
        :returns: Iterable über die Antwort‑Chunks des LLMs
        """
        raise NotImplementedError
