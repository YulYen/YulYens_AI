"""Runs the guard red-team corpus against a BasicGuard instance.

Shared on purpose: the pytest suite (``tests/test_guard_redteam.py``) and the
eval CLI both call ``evaluate_guard_case`` so the corpus has exactly one
meaning. No LLM involved — the guard is deterministic regex work, which is why
this part of the eval suite runs everywhere, including CI.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.corpus import GuardCase

# Which config flag a case depends on, derived from the reason it expects.
# Lets the CLI tell "the guard is broken" apart from "you switched that off".
PROTECTION_BY_REASON = {
    "wrongdoing": "wrongdoing_protection",
    "prompt_injection": "prompt_injection_protection",
    "pii_detected": "pii_protection",
    "blocked_keyword": "output_blocklist",
}


def required_protection(case: GuardCase) -> str | None:
    """The protection flag this case exercises, or None for benign cases."""
    reason = case.expect.get("reason")
    if isinstance(reason, str):
        return PROTECTION_BY_REASON.get(reason)
    if case.expect.get("masked") is True:
        return "pii_protection"
    if case.expect.get("blocked") is True:
        return "output_blocklist"
    return None


@dataclass(frozen=True)
class GuardOutcome:
    case_id: str
    stage: str
    failures: tuple[str, ...]
    observed: dict
    known_gap: bool = False
    note: str = ""
    # Set when the protection this case needs is disabled in the config: the
    # case says nothing about the guard's patterns then, only about the setup.
    skipped_protection: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures

    @property
    def skipped(self) -> bool:
        return self.skipped_protection is not None

    @property
    def counts_as_failure(self) -> bool:
        """Documented gaps and disabled protections must not fail the run."""
        return bool(self.failures) and not (self.known_gap or self.skipped)


def evaluate_guard_case(
    guard, case: GuardCase, disabled_protections: frozenset[str] = frozenset()
) -> GuardOutcome:
    """Check one corpus case against ``guard``.

    The guard carries session state (the wrongdoing lock), so callers must
    hand in a fresh instance per case — otherwise a lock armed by an earlier
    case would block later, unrelated ones.

    ``disabled_protections`` names flags the caller knows to be off (from the
    running config). A case that needs one of them is still evaluated, but the
    outcome is marked skipped rather than failed.
    """
    expect = case.expect
    observed: dict = {}
    failures: list[str] = []

    if case.stage == "input":
        result = guard.check_input(case.text)
        observed["ok"] = result["ok"]
        observed["reason"] = result["reason"]
        observed["detail"] = result.get("detail")
    elif case.stage == "context":
        # Abgerufener Fremdtext: die Frage ist nicht "blockiert der Guard das",
        # sondern "landet es im Prompt". Andere Regel als beim Eingang — ein
        # Artikel darf PII enthalten, eine Injection-Anweisung nicht.
        from security.tinyguard import context_rejection

        rejection = context_rejection(guard, case.text)
        observed["injected"] = rejection is None
        observed["reason"] = rejection or "ok"
    else:
        if "ok" in expect or "reason" in expect:
            result = guard.check_output(case.text)
            observed["ok"] = result["ok"]
            observed["reason"] = result["reason"]
            observed["detail"] = result.get("detail")
        if "blocked" in expect or "masked" in expect:
            processed = guard.process_output(case.text)
            observed["blocked"] = processed["blocked"]
            observed["masked"] = processed["masked"]
            observed["text"] = processed["text"]

    for key, expected in expect.items():
        if key not in observed:
            failures.append(f"{key}: nothing observed for this stage")
            continue
        actual = observed[key]
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")

    needed = required_protection(case)
    skipped = needed if (failures and needed in disabled_protections) else None

    return GuardOutcome(
        case_id=case.id,
        stage=case.stage,
        failures=tuple(failures),
        observed=observed,
        known_gap=case.known_gap,
        note=case.note,
        skipped_protection=skipped,
    )
