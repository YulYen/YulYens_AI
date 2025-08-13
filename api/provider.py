from typing import Protocol

class AnswerProvider(Protocol):
    def answer(self, question: str) -> str: ...
    

class EchoProvider:
    """Platzhalter: liefert nur ECHO zurück. Ersetzen wir in Schritt 2."""
    def answer(self, question: str) -> str:
        q = (question or "").strip()
        return f"[ECHO] {q}" if q else "[ECHO] (leere Frage)"
