"""
Core package of the YulYens_AI project.

This module provides key classes and interfaces for accessing different
language models. Through the :class:`LLMCore` interface various backends
can be implemented. By default an Ollama-based implementation and a
dummy for tests are available.
"""

from .llm_core import LLMCore  # noqa: F401

try:
    # Optionaler Import: Nur laden, wenn die ollama‑Bibliothek vorhanden ist
    from .ollama_llm_core import OllamaLLMCore  # type: ignore[assignment]
except Exception:
    OllamaLLMCore = None  # type: ignore[assignment]

from .dummy_llm_core import DummyLLMCore  # noqa: F401
from .streaming_provider import YulYenStreamingProvider  # noqa: F401

__all__ = [
    "LLMCore",
    "OllamaLLMCore",
    "DummyLLMCore",
    "YulYenStreamingProvider",
]
