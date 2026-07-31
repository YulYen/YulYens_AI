"""Core package of the YulYens_AI project.

Zugriff auf die LLM-Schnittstelle über die Untermodule:
``core.llm_core.LLMCore`` (abstrakt), ``core.ollama_llm_core.OllamaLLMCore``
(Produktion), ``core.dummy_llm_core.DummyLLMCore`` (Tests) und
``core.streaming_provider.YulYenStreamingProvider``.

**Bewusst leer.** Hier standen Re-Exports dieser vier Namen, und die machten
das Paket zyklisch: ``storage/__init__`` → ``storage.store`` → ``core.utils``
→ *dieses* ``__init__`` → ``streaming_provider`` → ``from storage import
ConversationStore``. Ergebnis:

    $ PYTHONPATH=src python -c "import storage"
    ImportError: cannot import name 'ConversationStore' from partially
    initialized module 'storage' (most likely due to a circular import)

Es fiel nur deshalb nie auf, weil jeder bestehende Einstiegspunkt zufällig
``core`` zuerst importiert. Wer ein Wartungs- oder Migrationsskript gegen die
Ablage schreibt, tritt sofort hinein. Die Re-Exports wurden projektweit
nirgends benutzt — ``from core import utils`` ist ein Submodul-Import und
funktioniert unabhängig vom Inhalt dieser Datei.
"""
