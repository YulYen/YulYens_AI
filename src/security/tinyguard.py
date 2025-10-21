from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any, TypedDict


class SecurityResult(TypedDict):
    ok: bool
    reason: str  # "ok" | "prompt_injection" | "pii_detected" | "blocked_keyword"
    detail: str | None  # first match / hint


_SECURITY_KEYS = (
    "security_prompt_injection",
    "security_pii_detected",
    "security_blocked_keyword",
    "security_all_clear",
)


def _load_texts(texts: Mapping[str, str] | None) -> Mapping[str, str]:
    if texts is not None:
        if not isinstance(texts, Mapping):
            raise TypeError("security texts must be provided as a mapping")
        return texts

    from config.config_singleton import Config  # lazy import to avoid cycles

    return Config().texts


def _require_security_text(locale_key: str, texts: Mapping[str, str]) -> str:
    try:
        value = texts[locale_key]
    except KeyError as exc:
        raise KeyError(
            f"Missing security text '{locale_key}'. Please add it to the locale catalog."
        ) from exc
    if not isinstance(value, str):  # pragma: no cover - defensive
        raise TypeError(f"Security text '{locale_key}' must be a string")
    return value


class BasicGuard:
    """
    Tiny, deterministic guard for v0.
    - check_input: prompt injection + PII
    - check_output: PII + output blocklist (API keys etc.)
    No network calls, no external dependencies.
    """

    def __init__(
        self,
        enabled: bool,
        prompt_injection_protection: bool,
        pii_protection: bool,
        output_blocklist: bool,
        custom_patterns: dict[str, list[str]] | None = None,
        texts: Mapping[str, str] | None = None,
    ):
        self.enabled = enabled
        self.flags = {
            "prompt_injection_protection": prompt_injection_protection,
            "pii_protection": pii_protection,
            "output_blocklist": output_blocklist,
        }

        self.texts = _load_texts(texts)
        for key in _SECURITY_KEYS:
            _require_security_text(key, self.texts)
        self.mask_text = _require_security_text("security_mask_text", self.texts)

        # Defaults (deliberately conservative and compact)
        inj = [
            r"(?i)\bignore (?:all|previous) (?:instructions|messages)",
            r"(?i)\bact as\b",
            r"(?i)\b(?:reveal|print|show).{0,30}\bsystem prompt\b",
            r"(?i)\byou are chatgpt\b",
            r"(?i)\bbegin system prompt\b",
            r"(?i)\bdeveloper mode\b",
            r"(?i)\b%?\{.*?\}%?",  # templating braces used in jailbreaks
            r"(?i)\bfile://|http://127\.0\.0\.1|localhost",
        ]

        de_inj = [
            # "Please ignore all previous instructions ..."
            r"(?i)\bignoriere\b.{0,80}\b(anweisungen|regeln|vorgaben)\b",
            r"(?i)\bübergehe\b.{0,80}\b(anweisungen|regeln|vorgaben)\b",
            # "Pretend you are root/admin/developer ..." / "Be root ..."
            r"(?i)\btu\s+so,\s*als\s+w(?:ä|ae)rst du\b.{0,30}\b(root|admin|entwickler|system)\b",
            r"(?i)\bsei\b.{0,20}\b(root|admin|entwickler|system)\b",
            r"(?i)\bagier(?:e)?\b.{0,20}\bals\b.{0,30}\b(root|admin|entwickler|system)\b",
            # "... output/show the system prompt"
            r"(?i)\b(zeige|gib)\b.{0,40}\b(system\s?prompt|systemprompt|system\-?prompt)\b.{0,40}\b(aus|anzeigen)\b",
            # Typical secret/file leak indicators
            r"(?i)/etc/passwd",
            r"(?i)\\windows\\system32\\config\\sam",
        ]
        inj += de_inj

        pii = [
            r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",  # E-Mail
            r"(?i)\b(?:\+?49|0)\s?(?:\d[\s\-()]{0,2}){7,}\d\b",  # DE-Telefon (grob)
            r"(?i)\bDE\d{20}\b",  # IBAN DE
        ]

        block = [
            r"(?i)\bsk-[A-Za-z0-9]{20,}\b",  # OpenAI style key
            r"(?i)\bghp_[A-Za-z0-9]{20,}\b",  # GitHub PAT
            r"(?i)\bAKIA[0-9A-Z]{16}\b",  # AWS Access Key
            r"(?i)\baws_secret_access_key\b.*?[A-Za-z0-9/+]{30,}",  # AWS Secret (heur.)
        ]

        if custom_patterns:
            if "prompt_injection" in custom_patterns:
                inj = custom_patterns["prompt_injection"]
            if "pii" in custom_patterns:
                pii = custom_patterns["pii"]
            if "output_blocklist" in custom_patterns:
                block = custom_patterns["output_blocklist"]

        self._inj = [re.compile(p, re.IGNORECASE) for p in inj]
        self._pii = [re.compile(p, re.IGNORECASE) for p in pii]
        self._block = [re.compile(p, re.IGNORECASE) for p in block]

    # ---- Public API -------------------------------------------------------

    def check_input(self, text: str) -> SecurityResult:
        if not self.enabled:
            return self._ok()

        if self.flags.get("prompt_injection_protection"):
            m = self._first_match(self._inj, text)
            if m:
                return self._bad("prompt_injection", m)

        if self.flags.get("pii_protection", True):
            m = self._first_match(self._pii, text)
            if m:
                return self._bad("pii_detected", m)

        return self._ok()

    def check_output(self, text: str) -> SecurityResult:
        if not self.enabled:
            return self._ok()

        if self.flags.get("pii_protection", True):
            m = self._first_match(self._pii, text)
            if m:
                return self._bad("pii_detected", m)

        if self.flags.get("output_blocklist"):
            m = self._first_match(self._block, text)
            if m:
                return self._bad("blocked_keyword", m)

        return self._ok()

    def process_output(self, text: str) -> dict:
        """
        Output policy decision (SRP: stays inside the guard).
        Returns:
        {
            "blocked": bool,            # True => show nothing (e.g. secret)
            "reason": str|None,         # e.g. "blocked_keyword"
            "text": str,                # masked text if applicable
            "masked": bool              # True when PII was masked
        }
        """
        if not self.enabled or not text:
            return {"blocked": False, "reason": None, "text": text, "masked": False}

        # 1) Block secrets (only if the flag is active)
        if self.flags.get("output_blocklist"):
            for rx in self._block:
                if rx.search(text):
                    return {
                        "blocked": True,
                        "reason": "blocked_keyword",
                        "text": "",
                        "masked": False,
                    }

        # 2) Mask PII (only if the flag is active)
        out = text
        masked = False
        if self.flags.get("pii_protection"):
            for rx in self._pii:
                new_out = rx.sub(self.mask_text, out)
                if new_out != out:
                    masked = True
                out = new_out

        return {"blocked": False, "reason": None, "text": out, "masked": masked}

    # ---- Helpers ----------------------------------------------------------

    def _first_match(self, patterns: list[re.Pattern], text: str) -> str | None:
        for r in patterns:
            hit = r.search(text)
            if hit:
                # Brief, harmless detail output
                frag = hit.group(0)
                return frag[:120]
        return None

    def _ok(self) -> SecurityResult:
        return {"ok": True, "reason": "ok", "detail": None}

    def _bad(self, reason: str, detail: str) -> SecurityResult:
        return {"ok": False, "reason": reason, "detail": detail}


# ---------------------------------------------------------------------------


class DisabledGuard(BasicGuard):
    """Stub variant that disables every check."""

    def __init__(self) -> None:
        super().__init__(
            enabled=False,
            prompt_injection_protection=False,
            pii_protection=False,
            output_blocklist=False,
        )


DISABLED_GUARD_NAMES = {"disabledguard", "disabled", "none", "off"}


def create_guard(name: str, settings: dict[str, Any]) -> BasicGuard:
    """Factory that instantiates known guard classes from the configuration."""

    normalized = (name or "").strip().lower()
    if not normalized:
        normalized = "basicguard"

    if normalized == "basicguard":
        return BasicGuard(
            enabled=bool(settings.get("enabled", True)),
            prompt_injection_protection=bool(
                settings.get("prompt_injection_protection", True)
            ),
            pii_protection=bool(settings.get("pii_protection", True)),
            output_blocklist=bool(settings.get("output_blocklist", True)),
            custom_patterns=settings.get("custom_patterns"),
        )

    if normalized in DISABLED_GUARD_NAMES:
        return DisabledGuard()

    raise ValueError(f"Unknown security guard: {name!r}")


# -- Optional: human-friendly warning with "Yul Yen's wagging finger"
def zeigefinger_message(
    res: SecurityResult, *, texts: Mapping[str, str] | None = None
) -> str:
    catalog = _load_texts(texts)
    reason = (res.get("reason") or "ok").lower()
    detail = (res.get("detail") or "")[:80]
    if reason == "prompt_injection":
        template = _require_security_text("security_prompt_injection", catalog)
        return template.format(detail=detail)
    if reason == "pii_detected":
        return _require_security_text("security_pii_detected", catalog)
    if reason == "blocked_keyword":
        return _require_security_text("security_blocked_keyword", catalog)
    return _require_security_text("security_all_clear", catalog)
