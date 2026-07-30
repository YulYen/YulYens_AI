"""Orchestration: corpus in, answers + verdicts out.

The answer source is injected as a callable so the runner is fully testable
without Ollama. In production ``build_answer_fn`` wires it to the same one-shot
provider the API uses — guard, wiki and logging included, so an eval run
exercises the real path instead of a shortcut.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from evals.checks import CheckFailure, run_checks
from evals.corpus import (
    BehaviourCorpus,
    GuardCorpus,
    KarlCorpus,
    PersonaCase,
    PersonaCorpus,
)
from evals.guard_eval import GuardOutcome, evaluate_guard_case
from evals.judge import Judge, JudgeVerdict

AnswerFn = Callable[[str, str], str]  # (persona, question) -> answer
SummarizeFn = Callable[[list[dict]], str]  # history -> summary text
GuardFactory = Callable[[], object]  # fresh guard per case (session state!)


@dataclass
class CaseResult:
    group: str  # "persona:DORIS" or "behaviour:three_timestamps"
    persona: str
    case_id: str
    question: str
    answer: str = ""
    check_failures: tuple[CheckFailure, ...] = ()
    verdict: JudgeVerdict | None = None
    error: str | None = None
    duration_ms: int = 0

    @property
    def checks_passed(self) -> bool:
        return not self.check_failures

    @property
    def traits_passed(self) -> bool:
        """True when a judge ran and every trait scored 4 or better."""
        if self.verdict is None:
            return True  # nothing to judge (or judge disabled) == no verdict
        return all(v.passed for v in self.verdict.verdicts)

    @property
    def passed(self) -> bool:
        return self.error is None and self.checks_passed and self.traits_passed


@dataclass
class EvalRun:
    model: str
    judge_model: str | None
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    results: list[CaseResult] = field(default_factory=list)
    guard_outcomes: list[GuardOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def errors(self) -> int:
        return sum(1 for r in self.results if r.error is not None)

    @property
    def guard_failed(self) -> int:
        return sum(1 for o in self.guard_outcomes if o.counts_as_failure)

    @property
    def guard_known_gaps(self) -> int:
        return sum(1 for o in self.guard_outcomes if o.known_gap and not o.passed)

    @property
    def guard_skipped(self) -> int:
        return sum(1 for o in self.guard_outcomes if o.skipped)

    @property
    def average_score(self) -> float | None:
        averages = [
            r.verdict.average
            for r in self.results
            if r.verdict is not None and r.verdict.average is not None
        ]
        if not averages:
            return None
        return round(sum(averages) / len(averages), 2)

    @property
    def ok(self) -> bool:
        return self.errors == 0 and self.guard_failed == 0 and self.passed == self.total


def build_answer_fn(factory) -> AnswerFn:
    """Wire answers to the shared one-shot provider (guard + wiki included)."""
    provider = factory.get_one_shot_provider()

    def _answer(persona: str, question: str) -> str:
        return provider.answer(question, persona)

    return _answer


def _run_case(
    group: str,
    persona: str,
    case: PersonaCase,
    answer_fn: AnswerFn,
    judge: Judge | None,
    today: date | None,
) -> CaseResult:
    result = CaseResult(
        group=group, persona=persona, case_id=case.id, question=case.question
    )
    started = time.monotonic()
    try:
        result.answer = answer_fn(persona, case.question)
    except Exception as exc:  # a broken model must not abort the whole run
        result.error = f"{type(exc).__name__}: {exc}"
        result.duration_ms = int((time.monotonic() - started) * 1000)
        return result

    result.check_failures = run_checks(result.answer, case.checks, today=today)

    if judge is not None and case.expect_traits:
        try:
            result.verdict = judge.score(
                case.question, result.answer, case.expect_traits
            )
        except Exception as exc:
            result.error = f"judge failed — {type(exc).__name__}: {exc}"

    result.duration_ms = int((time.monotonic() - started) * 1000)
    return result


def run_persona_corpora(
    corpora: Sequence[PersonaCorpus],
    answer_fn: AnswerFn,
    judge: Judge | None = None,
    today: date | None = None,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for corpus in corpora:
        for case in corpus.cases:
            results.append(
                _run_case(
                    f"persona:{corpus.persona}",
                    corpus.persona,
                    case,
                    answer_fn,
                    judge,
                    today,
                )
            )
    return results


def run_behaviour_corpora(
    corpora: Sequence[BehaviourCorpus],
    answer_fn: AnswerFn,
    judge: Judge | None = None,
    today: date | None = None,
) -> list[CaseResult]:
    results: list[CaseResult] = []
    for corpus in corpora:
        for case in corpus.cases:
            results.append(
                _run_case(
                    f"behaviour:{corpus.name}",
                    corpus.persona,
                    case,
                    answer_fn,
                    judge,
                    today,
                )
            )
    return results


def run_karl_corpus(
    corpus: KarlCorpus | None,
    summarize_fn: SummarizeFn,
    judge: Judge | None = None,
) -> list[CaseResult]:
    """Score Karl's summaries — closes the open quality point from #12."""
    if corpus is None:
        return []

    results: list[CaseResult] = []
    for case in corpus.cases:
        result = CaseResult(
            group=f"karl:{corpus.name}",
            persona="KARL",
            case_id=case.id,
            question=f"{len(case.history)} Nachrichten zusammenfassen",
        )
        started = time.monotonic()
        try:
            result.answer = summarize_fn([dict(m) for m in case.history])
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            result.duration_ms = int((time.monotonic() - started) * 1000)
            results.append(result)
            continue

        result.check_failures = run_checks(result.answer, case.checks)
        if judge is not None and case.expect_traits:
            try:
                result.verdict = judge.score(
                    "Fasse den Gesprächsverlauf zusammen.",
                    result.answer,
                    case.expect_traits,
                )
            except Exception as exc:
                result.error = f"judge failed — {type(exc).__name__}: {exc}"
        result.duration_ms = int((time.monotonic() - started) * 1000)
        results.append(result)
    return results


def run_guard_corpus(
    corpus: GuardCorpus,
    guard_factory: GuardFactory,
    disabled_protections: frozenset[str] = frozenset(),
) -> list:
    return [
        evaluate_guard_case(guard_factory(), case, disabled_protections)
        for case in corpus.cases
    ]
