"""
Core-Paket des YulYens_AI‑Projekts.

Dieses Modul stellt zentrale Klassen und Interfaces für den Zugriff auf
unterschiedliche Sprachmodelle bereit. Über das :class:`LLMCore`‑Interface
können verschiedene Backends implementiert werden. Standardmäßig steht
eine Ollama‑basierte Implementierung sowie ein Dummy für Tests zur Verfügung.
"""

from .llm_core import LLMCore # noqa: F401
try:
    # Optionaler Import: Nur laden, wenn die ollama‑Bibliothek vorhanden ist
    from .ollama_llm_core import OllamaLLMCore # type: ignore[assignment]
except Exception:
    OllamaLLMCore = None # type: ignore[assignment]

from .dummy_llm_core import DummyLLMCore # noqa: F401
from .streaming_provider import YulYenStreamingProvider # noqa: F401

__all__ = [
    "LLMCore",
    "OllamaLLMCore",
    "DummyLLMCore",
    "YulYenStreamingProvider",
]