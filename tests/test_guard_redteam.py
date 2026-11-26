"""The guard red-team corpus (#41) as real tests — no LLM involved.

Every case in tests/guard_redteam.yaml becomes one parametrized test, so new
attack patterns are added by editing the YAML, not this file. Fully offline,
which is why this runs in CI on every push.

Whether the *model* follows a payload that gets through is a different
question and measured in the lab (`python -m yulyen_lab probe`).
"""

import pytest
from yulyen_ai.security.tinyguard import BasicGuard

from tests.guard_corpus import CorpusError, evaluate_guard_case, load_guard_corpus

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
        "tests/guard_redteam.yaml so it is asserted from now on."
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


# Die Lücken, die wir *bewusst* mitführen. Weder mehr noch weniger.
#
# Die Liste war nach #62 leer, und das war der Punkt dieses Tests:
# `ctx_code_snippet_in_article_is_kept` stand hier als Abnahmekriterium, und
# als die Regel fiel, musste das Flag im Korpus fallen — die Richtung, die ein
# bloßes „keine Lücken" nie gemeldet hätte.
#
# Sie ist seit der Messung an echten ZIM-Artikeln (2026-08-07) wieder gefüllt,
# und zwar mit *gemessenen* statt vermuteten Lücken. Die Begründung steht bei
# jedem Fall im Korpus:
#
#   * fünf `ctx_*`: Nutzlasten, die der Guard nicht fängt **und** die
#     `ministral-3:8b` befolgt. Nicht jede durchgelassene Nutzlast steht hier;
#     von 27 durchgelassenen wirkten 7, und nur die sind eine Lücke mit Folgen.
#   * ein `ok_*`: ein Artikel *über* Prompt-Injection, der den Angriffssatz
#     zitiert. Anders als bei den Themenwörtern unten gibt es hier keine
#     erkennbare Naht zwischen Erwähnung und Anweisung — `ignoriere alle
#     vorherigen Anweisungen` ist derselbe Satz, ob zitiert oder gemeint.
#
# Drei `ok_*` sind **wieder verschwunden**, und zwar in der Richtung, für die
# es diesen Test gibt: `amoklauf_de` und `mass_shooting` verlangen jetzt einen
# Absichtsmarker, also bestehen die Definitionsfragen und der Artikel. Wer die
# Regeln zurückdreht, bekommt hier sofort einen roten Test statt einer stillen
# Verschlechterung.
#
# Die fünf `ctx_*` sind seit #91 (2026-11-10) geschlossen: jede hat eine Regel
# in `context_only`, die an der Anrede hängt. Übrig ist der eine Fehlalarm.
KNOWN_GAP_IDS: set[str] = {
    "ok_article_quoting_an_injection",
}


def test_repo_corpus_carries_exactly_the_gaps_we_decided_on():
    """Nicht „keine Lücken", sondern „genau diese".

    Der Test schlägt in **beide** Richtungen an: eine neue Lücke verlangt eine
    bewusste Entscheidung, und eine geschlossene verlangt, das Flag zu
    entfernen. „Keine Lücken" hätte den zweiten Fall nie gemeldet.
    """
    gaps = {case.id for case in CORPUS.cases if case.known_gap}
    assert gaps == KNOWN_GAP_IDS


# ---- Der Lader ist streng -------------------------------------------------


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_guard_input_case_rejects_output_only_expectations(tmp_path):
    _write(
        tmp_path,
        "guard_redteam.yaml",
        "cases:\n  - id: a\n    stage: input\n    text: t\n"
        "    expect:\n      blocked: true\n",
    )
    with pytest.raises(CorpusError, match="output cases only"):
        load_guard_corpus(tmp_path)


def test_guard_unknown_stage_is_rejected(tmp_path):
    _write(
        tmp_path,
        "guard_redteam.yaml",
        "cases:\n  - id: a\n    stage: sideways\n    text: t\n"
        "    expect:\n      ok: false\n",
    )
    with pytest.raises(CorpusError, match="'stage' must be one of"):
        load_guard_corpus(tmp_path)


def test_guard_known_gap_without_note_is_rejected(tmp_path):
    _write(
        tmp_path,
        "guard_redteam.yaml",
        "cases:\n  - id: a\n    stage: input\n    text: t\n"
        "    known_gap: true\n    expect:\n      ok: false\n",
    )
    with pytest.raises(CorpusError, match="needs a 'note'"):
        load_guard_corpus(tmp_path)


def test_guard_rule_without_a_blocking_reason_is_rejected(tmp_path):
    """`rule` sagt, *welche* Regel greifen soll — an einem sauberen Fall greift keine.

    Ohne diese Prüfung stünde in einem `ok`-Fall eine Erwartung, die nie
    erfüllbar ist: `check_input` liefert dort `rule: None`. Der Fall wäre
    dauerhaft rot, ohne dass am Guard etwas kaputt wäre.
    """
    _write(
        tmp_path,
        "guard_redteam.yaml",
        "cases:\n  - id: a\n    stage: input\n    text: t\n"
        "    expect:\n      ok: true\n      reason: ok\n      rule: irgendwas\n",
    )
    with pytest.raises(CorpusError, match="only makes sense together"):
        load_guard_corpus(tmp_path)


def test_guard_non_boolean_expectation_is_rejected(tmp_path):
    _write(
        tmp_path,
        "guard_redteam.yaml",
        "cases:\n  - id: a\n    stage: input\n    text: t\n"
        "    expect:\n      ok: maybe\n",
    )
    with pytest.raises(CorpusError, match="must be a boolean"):
        load_guard_corpus(tmp_path)
