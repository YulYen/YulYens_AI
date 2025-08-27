"""
Lightweight Security for Yul Yen’s AI Orchestra


This drop replaces the earlier regex-heavy approach with two tiny, local-first providers:
- Rebuff → Prompt‑Injection‑Detektion
- Presidio → PII‑Erkennung (personenbezogene Daten)


Files:
1) security_checkers.py
2) security_providers.py
3) tests/test_security_lightweight.py


Install:
pip install rebuff presidio-analyzer presidio-anonymizer pytest


TODO: Update der requirements.txt
"""


# =============================
# File: security_checkers.py
# =============================
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


BLOCK_MESSAGE = "Yul Yen hebt den Zeigefinger ...."


@dataclass
class CheckResult:
    allowed: bool
    message: str = ""
    reason: str = ""


class SecurityChecker:
    """Minimal Interface für Eingabeprüfungen vor dem LLM-Routing."""
    name: str = "base"


    def __init__(self, *, max_chars: int = 10_000) -> None:
        self.max_chars = max_chars


    def check(self, text: str, *, user_id: Optional[str] = None, metadata: Optional[Dict] = None) -> CheckResult: # pragma: no cover (Interface)
        raise NotImplementedError


    def sanitize(self, text: str) -> str: # optional hook
        return text


class SingleUserLocalChecker(SecurityChecker):
    """Sehr schlanke Checks für vertrauenswürdigen lokalen Einzelnutzer.
    Nur grobe Längenbremse – sonst kein Overhead.
    """
    name = "single_user_local"


    def __init__(self, *, max_chars: int = 20_000) -> None:
        super().__init__(max_chars=max_chars)


    def check(self, text: str, *, user_id: Optional[str] = None, metadata: Optional[Dict] = None) -> CheckResult:
        if not text:
            return CheckResult(True)
        if len(text) > self.max_chars:
            return CheckResult(False, BLOCK_MESSAGE, reason=f"input_too_long>{len(text)}>{self.max_chars}")
        return CheckResult(True)




class SecurityCheckerFactory:
    """Erzeugt Checker anhand der Config.
    cfg: {"Security": "single_user_local"|"remote_user"}
    """
    @staticmethod
    def from_config(cfg: Dict) -> SecurityChecker:
        mode = (cfg.get("Security") or cfg.get("security") or "single_user_local").strip().lower()
        if mode == "single_user_local":
            return SingleUserLocalChecker()
        if mode == "remote_user":
            from security.security_providers import RemoteLightweightChecker
            return RemoteLightweightChecker()
        raise ValueError(f"Unknown Security mode: {mode}")


    # Sketch: Integration in StreamingCore
    #class StreamingCore:
    #def __init__(self, checker: SecurityChecker):
    #self.checker = checker


    #def route_user_input(self, text: str, **meta):
    #res = self.checker.check(text, metadata=meta)
    #if not res.allowed:
    #return {"ok": False, "error": BLOCK_MESSAGE, "reason": res.reason}
    #return {"ok": True, "forwarded": text}