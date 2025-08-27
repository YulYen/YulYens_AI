# =============================
# File: security_providers.py
# =============================
from __future__ import annotations

from typing import Dict, Optional
from dataclasses import dataclass

from security.checker import SecurityChecker, CheckResult, BLOCK_MESSAGE

# --- Rebuff (Prompt‑Injection) ------------------------------------------------
from pytector import PromptInjectionDetector


class PytectorChecker(SecurityChecker):
    """Lokaler Prompt‑Injection‑Checker basierend auf Pytector."""

    name = "pytector"

    def __init__(self, model_name: str = "deberta", threshold: float = 0.5, max_chars: int = 8000):
        super().__init__(max_chars=max_chars)
        # Pytector verwendet lokale Transformer‑Modelle; kein API‑Key nötig.
        self.detector = PromptInjectionDetector(model_name_or_url=model_name)
        self.threshold = threshold

    def check(self, text: str, **_):
        # Leere Eingaben zulassen
        if not text:
            return CheckResult(True)
        # Zu lange Eingaben blocken
        if len(text) > self.max_chars:
            return CheckResult(False, BLOCK_MESSAGE,
                               reason=f"input_too_long>{len(text)}>{self.max_chars}")
        # Analyse mit Pytector durchführen
        is_injection, probability = self.detector.detect_injection(text)  # z. B. (True, 0.82)
        # Blocken, wenn potenzielle Injektion und Wahrscheinlichkeit >= Schwellenwert
        if is_injection and probability >= self.threshold:
            return CheckResult(False, BLOCK_MESSAGE,
                               reason=f"prompt_injection_prob={probability:.2f}")
        # Sonst freigeben
        return CheckResult(True)

# --- Presidio (PII) -----------------------------------------------------------
from presidio_analyzer import AnalyzerEngine

class PresidioChecker(SecurityChecker):
    name = "presidio"

    def __init__(self, *, max_pii_findings: int = 2, language: str = "en", max_chars: int = 8_000) -> None:
        super().__init__(max_chars=max_chars)
        self.max_pii = max_pii_findings
        self.language = language
        self.analyzer = AnalyzerEngine()

    def check(self, text: str, *, user_id: Optional[str] = None, metadata: Optional[Dict] = None) -> CheckResult:
        if not text:
            return CheckResult(True)
        if len(text) > self.max_chars:
            return CheckResult(False, BLOCK_MESSAGE, reason=f"input_too_long>{len(text)}>{self.max_chars}")
        findings = self.analyzer.analyze(text=text, entities=None, language=self.language)
        if len(findings) > self.max_pii:
            return CheckResult(False, BLOCK_MESSAGE, reason=f"bulk_pii_findings={len(findings)}")
        return CheckResult(True)

# --- Kombi für remote_user ----------------------------------------------------
class RemoteLightweightChecker(SecurityChecker):
    name = "remote_user_light"

    def __init__(self, *, max_chars: int = 8_000, inj_threshold: float = 0.5, max_pii_findings: int = 2, language: str = "en") -> None:
        super().__init__(max_chars=max_chars)
        self.inj = PytectorChecker(threshold=inj_threshold, max_chars=max_chars)
        self.pii = PresidioChecker(max_pii_findings=max_pii_findings, language=language, max_chars=max_chars)

    def check(self, text: str, **meta) -> CheckResult:
        r = self.inj.check(text, **meta)
        if not r.allowed:
            return r
        return self.pii.check(text, **meta)



