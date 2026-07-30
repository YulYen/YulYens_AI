"""Live parts of the eval suite (#41) — skipped without a reachable Ollama.

These cover the one assumption the offline tests cannot check: that a real 8B
model actually answers the judge prompt in the requested format. Everything
else about the suite is verified offline.

Deliberately no assertions on answer quality — that is what the eval *report*
is for. A test that fails because the model was in a bad mood is worse than no
test.
"""

import pytest
from core.factory import AppFactory

from evals.corpus import load_persona_corpora
from evals.judge import Judge
from evals.runner import build_answer_fn, run_persona_corpora


@pytest.mark.ollama
@pytest.mark.slow
def test_judge_returns_parsable_scores_from_a_real_model(ollama_config):
    """The judge output contract: one parsable score per trait."""
    factory = AppFactory()
    judge = Judge(
        llm_core=factory.get_llm_core(),
        model_name=str(ollama_config.core["model_name"]),
        keep_alive=int(ollama_config.core.get("keep_alive", 600)),
    )

    traits = (
        "nennt Paris als Hauptstadt von Frankreich",
        "bleibt bei maximal zwei Sätzen",
    )
    verdict = judge.score(
        "Was ist die Hauptstadt von Frankreich?",
        "Paris. Wusstest du das wirklich nicht?",
        traits,
    )

    assert verdict.raw, "judge returned nothing at all"
    scored = [v for v in verdict.verdicts if v.score is not None]
    assert scored, (
        "no score could be parsed from the judge answer — the prompt format "
        f"contract broke. Raw answer was:\n{verdict.raw}"
    )
    assert verdict.average is not None


@pytest.mark.ollama
@pytest.mark.slow
def test_one_persona_corpus_runs_end_to_end(ollama_config):
    """Answers + checks + judge against the real model, one persona only."""
    factory = AppFactory()
    corpora = [c for c in load_persona_corpora() if c.persona == "PETER"]
    assert corpora, "PETER corpus missing"

    judge = Judge(
        llm_core=factory.get_llm_core(),
        model_name=str(ollama_config.core["model_name"]),
    )
    results = run_persona_corpora(corpora, build_answer_fn(factory), judge)

    assert len(results) == len(corpora[0].cases)
    for result in results:
        assert result.error is None, result.error
        assert result.answer.strip(), f"{result.case_id} produced an empty answer"
        assert result.verdict is not None
