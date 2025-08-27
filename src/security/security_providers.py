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
    """
    Leichter Prompt-Injection-Checker.
    mode="keyword": kein Modell-Download, nur Keyword-Blocking (schnell).
    mode="model":   lädt ein lokales HF-Modell (z. B. DeBERTa) – kann dauern.
    """
    name = "pytector"

    def __init__(
        self,
        *,
        mode: str = "keyword",
        model_name: str = "deberta",
        inj_threshold: float = 0.5,
        max_chars: int = 8000,
    ):
        super().__init__(max_chars=max_chars)
        self.mode = mode
        self.inj_threshold = inj_threshold

        if PromptInjectionDetector is None:
            # Kein pytector installiert → permissiv (Tests können per monkeypatch c.detector setzen)
            self.detector = None
            self.use_score = False
            return

        if mode == "keyword":
            # sofort einsatzbereit, keine Modelle nötig
            self.detector = PromptInjectionDetector(
                keyword_blocking=True,
                input_keywords=[
                    "ignore instructions", "reveal system prompt",
                    "bypass safety", "jailbreak", "act as dan"
                ],
                output_keywords=[],
            )
            self.use_score = False
        elif mode == "model":
            self.detector = PromptInjectionDetector(model_name_or_url=model_name)
            self.use_score = True
        else:
            raise ValueError(f"Unknown Pytector mode: {mode}")

    def check(self, text: str, **_) -> CheckResult:
        if not text:
            return CheckResult(True)
        if len(text) > self.max_chars:
            return CheckResult(False, BLOCK_MESSAGE,
                               reason=f"input_too_long>{len(text)}>{self.max_chars}")

        if self.detector is None:
            # Fallback: ohne Detector nicht blocken (Unit-Tests mocken den Detector)
            return CheckResult(True)

        is_inj, prob = self.detector.detect_injection(text)  # (bool, float|None)
        if self.use_score:
            prob = float(prob or 0.0)
            if is_inj and prob >= self.inj_threshold:
                return CheckResult(False, BLOCK_MESSAGE,
                                   reason=f"prompt_injection_prob={prob:.2f}")
            return CheckResult(True)
        else:
            if is_inj:
                return CheckResult(False, BLOCK_MESSAGE,
                                   reason="prompt_injection_keyword_block")
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



