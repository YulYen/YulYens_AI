"""The guard red-team corpus (#41) as real tests — no LLM involved.

Every case in evals/guard_redteam.yaml becomes one parametrized test, so new
attack patterns are added by editing the YAML, not this file. Fully offline,
which is why this runs in CI on every push.
"""

import pytest
from evals.corpus import load_guard_corpus
from evals.guard_eval import evaluate_guard_case
from security.tinyguard import BasicGuard

CUSTOM_TEXTS = {
    "security_mask_text": "[mask]",
    "security_prompt_injection": "Prompt blocked ({detail})",
    "security_pii_detected": "PII blocked",
    "security_blocked_keyword": "Secrets blocked",
    "security_wrongdoing": "Refused: no harm instructions",
    "security_all_clear": "All clear",
}

CORPUS = load_guard_corpus()


def _fresh_guard() -> BasicGuard:
    # One instance per case: the wrongdoing lock is session state.
    return BasicGuard(
        enabled=True,
        prompt_injection_protection=True,
        pii_protection=True,
        output_blocklist=True,
        wrongdoing_protection=True,
        texts=CUSTOM_TEXTS,
    )


def test_corpus_is_not_empty_and_covers_all_three_stages():
    """Drei Kanäle, drei Stufen.

    „context" ist der abgerufene Fremdtext (Wikipedia-Snippet, RSS-Meldung),
    der als `system`-Nachricht in den Prompt geht. Er hat eigene Regeln — PII
    ist dort erlaubt, eine Injection-Anweisung nicht — und war lange gar nicht
    abgedeckt, weil der Guard ihn schlicht nie gesehen hat.
    """
    stages = {case.stage for case in CORPUS.cases}
    assert stages == {"input", "output", "context"}
    # Guardrail against a corpus that only ever asserts "blocked": benign
    # traffic must be represented too, or the tests would pass with a guard
    # that refuses everything.
    benign = [
        c
        for c in CORPUS.cases
        if c.expect.get("ok") is True or c.expect.get("injected") is True
    ]
    assert len(benign) >= 4


ASSERTED_CASES = [c for c in CORPUS.cases if not c.known_gap]
GAP_CASES = [c for c in CORPUS.cases if c.known_gap]


@pytest.mark.parametrize("case", ASSERTED_CASES, ids=lambda c: c.id)
def test_guard_matches_corpus_expectation(case):
    outcome = evaluate_guard_case(_fresh_guard(), case)
    assert outcome.passed, (
        f"{case.id} ({case.stage}): {'; '.join(outcome.failures)} "
        f"— observed {outcome.observed}"
    )


@pytest.mark.parametrize("case", GAP_CASES, ids=lambda c: c.id)
def test_known_gaps_are_still_gaps(case):
    """Documented weaknesses, asserted from the other side.

    If one of these starts passing, the guard got better and the case should
    lose its ``known_gap`` flag — so this test fails on purpose to say so.
    """
    outcome = evaluate_guard_case(_fresh_guard(), case)
    assert not outcome.passed, (
        f"{case.id} now satisfies its expectation — remove 'known_gap' from "
        "evals/guard_redteam.yaml so it is asserted from now on."
    )


def test_disabled_guard_lets_attacks_through():
    """Sanity check that the corpus actually depends on the guard being on."""
    guard = BasicGuard(
        enabled=False,
        prompt_injection_protection=True,
        pii_protection=True,
        output_blocklist=True,
        wrongdoing_protection=True,
        texts=CUSTOM_TEXTS,
    )
    attacks = [c for c in CORPUS.cases if c.expect.get("ok") is False]
    assert attacks, "corpus should contain attacks"
    satisfied = [case.id for case in attacks if evaluate_guard_case(guard, case).passed]
    assert (
        not satisfied
    ), f"a disabled guard must not satisfy attack expectations: {satisfied}"
