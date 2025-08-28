from __future__ import annotations
import re
from typing import TypedDict, Optional, Dict, List


class SecurityResult(TypedDict):
    ok: bool
    reason: str           # "ok" | "prompt_injection" | "pii_detected" | "blocked_keyword"
    detail: Optional[str] # erster Match / Hinweis


class BasicGuard:
    """
    Winziger, deterministischer Guard für v0.
    - check_input: Prompt-Injection + PII
    - check_output: PII + Output-Blocklist (API-Keys etc.)
    Keine Netz-Calls, keine externen Abhängigkeiten.
    """

    def __init__(
        self,
        enabled: bool = True,
        prompt_injection_protection: bool = True,
        pii_protection: bool = True,
        output_blocklist: bool = True,
        custom_patterns: Optional[Dict[str, List[str]]] = None,
    ):
        self.enabled = enabled
        self.flags = {
            "prompt_injection_protection": prompt_injection_protection,
            "pii_protection": pii_protection,
            "output_blocklist": output_blocklist,
        }

        # Defaults (bewusst konservativ & klein halten)
        inj = [
            r"(?i)\bignore (?:all|previous) (?:instructions|messages)",
            r"(?i)\bact as\b",
            r"(?i)\b(?:reveal|print|show).{0,30}\bsystem prompt\b",
            r"(?i)\byou are chatgpt\b",
            r"(?i)\bbegin system prompt\b",
            r"(?i)\bdeveloper mode\b",
            r"(?i)\b%?\{.*?\}%?",         # templating braces used in jailbreaks
            r"(?i)\bfile://|http://127\.0\.0\.1|localhost",
        ]

        de_inj = [
            # "Bitte ignoriere alle bisherigen Anweisungen ..."
            r"(?i)\bignoriere\b.{0,80}\b(anweisungen|regeln|vorgaben)\b",
            r"(?i)\bübergehe\b.{0,80}\b(anweisungen|regeln|vorgaben)\b",

            # "Tu so, als wärst du root/admin/entwickler ..." / "Sei root ..."
            r"(?i)\btu\s+so,\s*als\s+w(?:ä|ae)rst du\b.{0,30}\b(root|admin|entwickler|system)\b",
            r"(?i)\bsei\b.{0,20}\b(root|admin|entwickler|system)\b",
            r"(?i)\bagier(?:e)?\b.{0,20}\bals\b.{0,30}\b(root|admin|entwickler|system)\b",

            # "… gib/zeige den Systemprompt aus/anzeigen"
            r"(?i)\b(zeige|gib)\b.{0,40}\b(system\s?prompt|systemprompt|system\-?prompt)\b.{0,40}\b(aus|anzeigen)\b",

            # typische Geheimnis-/Datei-Leak-Indikatoren
            r"(?i)/etc/passwd",
            r"(?i)\\windows\\system32\\config\\sam",
        ]
        inj += de_inj

        pii = [
            r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",                # E-Mail
            r"(?i)\b(?:\+?49|0)\s?(?:\d[\s\-()]{0,2}){7,}\d\b",              # DE-Telefon (grob)
            r"(?i)\bDE\d{20}\b",                                             # IBAN DE
        ]

        block = [
            r"(?i)\bsk-[A-Za-z0-9]{20,}\b",                                  # OpenAI style key
            r"(?i)\bghp_[A-Za-z0-9]{20,}\b",                                 # GitHub PAT
            r"(?i)\bAKIA[0-9A-Z]{16}\b",                                     # AWS Access Key
            r"(?i)\baws_secret_access_key\b.*?[A-Za-z0-9/+]{30,}",           # AWS Secret (heur.)
        ]

        if custom_patterns:
            inj = custom_patterns.get("prompt_injection", inj) or inj
            pii = custom_patterns.get("pii", pii) or pii
            block = custom_patterns.get("output_blocklist", block) or block

        self._inj = [re.compile(p, re.IGNORECASE) for p in inj]
        self._pii = [re.compile(p, re.IGNORECASE) for p in pii]
        self._block = [re.compile(p, re.IGNORECASE) for p in block]

    # ---- Public API -------------------------------------------------------

    def check_input(self, text: str) -> SecurityResult:
        if not self.enabled:
            return self._ok()

        if self.flags["prompt_injection_protection"]:
            m = self._first_match(self._inj, text)
            if m:
                return self._bad("prompt_injection", m)

        if self.flags["pii_protection"]:
            m = self._first_match(self._pii, text)
            if m:
                return self._bad("pii_detected", m)

        return self._ok()

    def check_output(self, text: str) -> SecurityResult:
        if not self.enabled:
            return self._ok()

        if self.flags["pii_protection"]:
            m = self._first_match(self._pii, text)
            if m:
                return self._bad("pii_detected", m)

        if self.flags["output_blocklist"]:
            m = self._first_match(self._block, text)
            if m:
                return self._bad("blocked_keyword", m)

        return self._ok()

    # ---- Helpers ----------------------------------------------------------

    def _first_match(self, patterns: List[re.Pattern], text: str) -> Optional[str]:
        for r in patterns:
            hit = r.search(text)
            if hit:
                # kurze, harmlose Detailausgabe
                frag = hit.group(0)
                return frag[:120]
        return None

    def _ok(self) -> SecurityResult:
        return {"ok": True, "reason": "ok", "detail": None}

    def _bad(self, reason: str, detail: str) -> SecurityResult:
        return {"ok": False, "reason": reason, "detail": detail}