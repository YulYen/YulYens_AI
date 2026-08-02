"""Checks, judge parsing, runner and report (#41) — all without a real model.

The answer source and the judge are injected, so the whole orchestration is
testable offline. That is deliberate: the suite must be trustworthy before it
is pointed at a model.
"""

from datetime import date

import pytest

from evals.checks import expand, placeholders, run_checks
from evals.corpus import (
    BehaviourCorpus,
    Checks,
    GuardCorpus,
    KarlCase,
    KarlCorpus,
    PersonaCase,
    PersonaCorpus,
)
from evals.judge import Judge, build_prompt, parse_verdict
from evals.report import CSV_COLUMNS, render_csv, render_markdown
from evals.runner import (
    EvalRun,
    run_behaviour_corpora,
    run_guard_corpus,
    run_karl_corpus,
    run_persona_corpora,
)
from tests.doubles import permissive_guard_double

# ---- Deterministic checks -------------------------------------------------


def test_must_match_is_case_insensitive_and_multiline():
    checks = Checks(must_match=("paris",))
    assert run_checks("Die Hauptstadt ist\nPARIS.", checks) == ()


def test_must_match_reports_missing_pattern():
    failures = run_checks("Berlin", Checks(must_match=("paris",)))
    assert len(failures) == 1
    assert failures[0].kind == "must_match"


def test_must_not_match_reports_the_hit():
    failures = run_checks("Gerne helfe ich dir", Checks(must_not_match=("gerne",)))
    assert failures[0].kind == "must_not_match"
    assert "Gerne" in failures[0].detail


def test_length_bounds_are_enforced():
    assert run_checks("x" * 11, Checks(max_chars=10))[0].kind == "max_chars"
    assert run_checks("x", Checks(min_chars=5))[0].kind == "min_chars"


def test_empty_checks_never_fail():
    assert run_checks("anything", Checks()) == ()


def test_placeholders_are_substituted_with_the_run_date():
    values = placeholders(date(2026, 7, 30))
    assert values["today_iso"] == "2026-07-30"
    assert values["today_de"] == "30. Juli 2026"
    assert (
        run_checks(
            "Heute ist der 30. Juli 2026.",
            Checks(must_match=("{today_de}",)),
            today=date(2026, 7, 30),
        )
        == ()
    )


def test_placeholder_values_are_regex_escaped():
    # A literal dot in "30. Juli" must not act as a regex wildcard.
    pattern = expand("{today_de}", placeholders(date(2026, 7, 30)))
    assert r"30\." in pattern


def test_unknown_placeholder_is_left_alone():
    assert expand("{nope}", placeholders(date(2026, 7, 30))) == "{nope}"


# ---- Judge ---------------------------------------------------------------


def test_build_prompt_numbers_the_traits():
    messages = build_prompt("Frage?", "Antwort.", ("erste", "zweite"))
    user = messages[1]["content"]
    assert "1. erste" in user and "2. zweite" in user


def test_parse_verdict_reads_scores_and_reasons():
    verdict = parse_verdict("1: 5 | trifft zu\n2: 2 | verfehlt", ("a", "b"))
    assert [v.score for v in verdict.verdicts] == [5, 2]
    assert verdict.verdicts[0].reason == "trifft zu"
    assert verdict.average == 3.5


def test_parse_verdict_marks_missing_lines_as_unscored():
    verdict = parse_verdict("1: 4 | ok", ("a", "b"))
    assert verdict.verdicts[1].score is None
    assert verdict.unscored == ("b",)
    # A judge that did not answer must never look like a pass.
    assert verdict.verdicts[1].passed is False


def test_parse_verdict_survives_chatty_judges():
    raw = "Hier meine Bewertung:\n\n1) 5 - passt\n2. 3 | nur teilweise\nDanke!"
    verdict = parse_verdict(raw, ("a", "b"))
    assert [v.score for v in verdict.verdicts] == [5, 3]


def test_parse_verdict_reads_the_line_a_real_judge_actually_wrote():
    # Verbatim from the failing live run (#71): the format was kept, the
    # model just wrote the score in bold.
    raw = "1: **5** | Hauptstadt korrekt genannt\n2: **2** | mehr als zwei Sätze"
    verdict = parse_verdict(raw, ("a", "b"))
    assert [v.score for v in verdict.verdicts] == [5, 2]
    assert verdict.verdicts[0].reason == "Hauptstadt korrekt genannt"


@pytest.mark.parametrize(
    "line",
    [
        "1: **5** | gut",
        "**1**: 5 | gut",
        "**1: 5** | gut",
        "1: `5` | gut",
        "1: __5__ | gut",
        "- 1: **5** | gut",
        "* **1.** 5 — gut",
        "1: Punktzahl: 5 | gut",
        "1) **Bewertung 5** – gut",
        "1: 5/5 | gut",
    ],
)
def test_parse_verdict_tolerates_markdown_decoration(line):
    verdict = parse_verdict(line, ("a",))
    assert verdict.verdicts[0].score == 5
    assert verdict.verdicts[0].reason == "gut"


@pytest.mark.parametrize(
    "raw",
    [
        "Die Antwort war gut.\n1 Satz reicht völlig aus.",
        "Insgesamt 5 von 5 Erwartungen erfüllt.",
        "1. Satz: die Hauptstadt stimmt.",
        "1: 7 | ausserhalb der Skala",
        "1: 0 | ausserhalb der Skala",
        "Bewertung folgt später.",
    ],
)
def test_parse_verdict_still_refuses_digits_from_running_text(raw):
    # The looser pattern must not turn any number into a score — an
    # unanswered trait has to keep failing loudly (#71).
    verdict = parse_verdict(raw, ("a",))
    assert verdict.verdicts[0].score is None
    assert verdict.average is None


def test_parse_verdict_ignores_out_of_range_indices():
    verdict = parse_verdict("7: 5 | nonsense", ("a",))
    assert verdict.verdicts[0].score is None
    assert verdict.average is None


def test_score_three_is_not_a_pass():
    verdict = parse_verdict("1: 3 | halb", ("a",))
    assert verdict.verdicts[0].passed is False


class _FakeCore:
    """Minimal LLMCore stand-in that replays a fixed answer."""

    def __init__(self, text="1: 5 | gut"):
        self.text = text
        self.calls = []

    def stream_chat(self, model_name, messages, options=None, keep_alive=600):
        self.calls.append(
            {"model": model_name, "messages": messages, "options": options}
        )
        for chunk in self.text.split(" "):
            yield {"message": {"content": chunk + " "}}


def test_judge_uses_temperature_zero_and_the_configured_model():
    core = _FakeCore()
    verdict = Judge(core, "judge-model").score("q", "a", ("trait",))
    assert verdict.verdicts[0].score == 5
    assert core.calls[0]["model"] == "judge-model"
    assert core.calls[0]["options"]["temperature"] == 0.0


def test_judge_without_traits_does_not_call_the_model():
    core = _FakeCore()
    verdict = Judge(core, "m").score("q", "a", ())
    assert verdict.verdicts == ()
    assert core.calls == []


# ---- Runner --------------------------------------------------------------


def _persona_corpus(**case_kwargs):
    defaults = dict(
        id="c1",
        question="Frage?",
        expect_traits=("ist freundlich",),
        checks=Checks(),
        source="test.yaml",
    )
    defaults.update(case_kwargs)
    return PersonaCorpus(
        persona="DORIS", cases=(PersonaCase(**defaults),), source="test.yaml"
    )


def test_runner_records_answer_and_passes_when_everything_is_met():
    corpus = _persona_corpus(checks=Checks(must_match=("paris",)))
    judge = Judge(_FakeCore("1: 5 | ja"), "m")
    results = run_persona_corpora([corpus], lambda p, q: "Paris.", judge)
    assert len(results) == 1
    assert results[0].answer == "Paris."
    assert results[0].passed


def test_runner_marks_failed_checks_without_asking_the_judge_to_rescue_it():
    corpus = _persona_corpus(checks=Checks(must_match=("paris",)))
    judge = Judge(_FakeCore("1: 5 | ja"), "m")
    results = run_persona_corpora([corpus], lambda p, q: "Berlin.", judge)
    assert not results[0].passed
    assert results[0].check_failures


def test_runner_fails_the_case_when_a_trait_scores_low():
    judge = Judge(_FakeCore("1: 2 | nein"), "m")
    results = run_persona_corpora([_persona_corpus()], lambda p, q: "x", judge)
    assert not results[0].passed
    assert results[0].traits_passed is False


def test_runner_captures_answer_errors_and_keeps_going():
    def _boom(persona, question):
        raise RuntimeError("ollama down")

    corpora = [_persona_corpus(), _persona_corpus()]
    results = run_persona_corpora(corpora, _boom)
    assert len(results) == 2
    assert all(r.error and "ollama down" in r.error for r in results)
    assert all(not r.passed for r in results)


def test_runner_captures_judge_errors_as_case_errors():
    class _BrokenJudge:
        def score(self, *_args):
            raise RuntimeError("judge exploded")

    results = run_persona_corpora([_persona_corpus()], lambda p, q: "x", _BrokenJudge())
    assert "judge exploded" in results[0].error


def test_runner_without_judge_skips_trait_scoring():
    results = run_persona_corpora([_persona_corpus()], lambda p, q: "x")
    assert results[0].verdict is None
    assert results[0].passed  # no checks, no judge -> nothing to fail


def test_behaviour_runner_uses_the_corpus_persona_and_group():
    corpus = BehaviourCorpus(
        name="three_timestamps",
        persona="PETER",
        description="",
        cases=(
            PersonaCase(
                id="ts",
                question="Datum?",
                expect_traits=(),
                checks=Checks(must_match=("{year}",)),
                source="t.yaml",
            ),
        ),
        source="t.yaml",
    )
    asked = []
    results = run_behaviour_corpora(
        [corpus], lambda p, q: asked.append((p, q)) or f"Heute ist {date.today().year}."
    )
    assert asked == [("PETER", "Datum?")]
    assert results[0].group == "behaviour:three_timestamps"
    assert results[0].passed


def test_karl_runner_scores_the_summary():
    corpus = KarlCorpus(
        name="karl_summary",
        description="",
        cases=(
            KarlCase(
                id="k1",
                history=({"role": "user", "content": "Ich bin Yul."},),
                expect_traits=("nennt Yul",),
                checks=Checks(must_match=("yul",)),
                source="k.yaml",
            ),
        ),
        source="k.yaml",
    )
    judge = Judge(_FakeCore("1: 5 | ja"), "m")
    results = run_karl_corpus(
        corpus, lambda history: "Yul arbeitet an Orchestra.", judge
    )
    assert results[0].group == "karl:karl_summary"
    assert results[0].persona == "KARL"
    assert results[0].passed


def test_karl_runner_without_corpus_returns_nothing():
    assert run_karl_corpus(None, lambda history: "x") == []


# ---- Guard corpus integration -------------------------------------------


def test_guard_runner_gets_a_fresh_guard_per_case():
    from evals.corpus import GuardCase

    made = []

    def _factory():
        guard = permissive_guard_double()
        made.append(guard)
        return guard

    corpus = GuardCorpus(
        description="",
        cases=(
            GuardCase("a", "input", "t", {"ok": False}, "g.yaml"),
            GuardCase("b", "input", "t", {"ok": False}, "g.yaml"),
        ),
        source="g.yaml",
    )
    outcomes = run_guard_corpus(corpus, _factory)
    assert len(made) == 2 and made[0] is not made[1]
    assert all(not o.passed for o in outcomes)


def test_known_gap_does_not_count_as_failure():
    from evals.corpus import GuardCase

    corpus = GuardCorpus(
        description="",
        cases=(
            GuardCase(
                "gap",
                "input",
                "t",
                {"ok": False},
                "g.yaml",
                known_gap=True,
                note="documented",
            ),
        ),
        source="g.yaml",
    )
    run = EvalRun(model="m", judge_model=None)
    run.guard_outcomes = run_guard_corpus(corpus, permissive_guard_double)
    assert run.guard_failed == 0
    assert run.guard_known_gaps == 1
    assert run.ok


# ---- Report --------------------------------------------------------------


def _run_with_one_failure():
    judge = Judge(_FakeCore("1: 1 | verfehlt"), "judge-model")
    run = EvalRun(model="chat-model", judge_model="judge-model")
    run.results = run_persona_corpora([_persona_corpus()], lambda p, q: "x", judge)
    return run


def _run_with_average(judge_text, **case_kwargs):
    judge = Judge(_FakeCore(judge_text), "judge-model")
    run = EvalRun(model="chat-model", judge_model="judge-model")
    run.results = run_persona_corpora(
        [_persona_corpus(**case_kwargs)], lambda p, q: "x", judge
    )
    return run


def test_markdown_report_names_models_and_the_bias_warning():
    markdown = render_markdown(_run_with_one_failure())
    assert "chat-model" in markdown
    assert "judge-model" in markdown
    assert "Judge-Bias" in markdown


def test_the_bias_note_no_longer_claims_what_the_measurement_did_not_show():
    """#41a maß den Selbstbewertungs-Bias und fand ihn *nicht* belegt.

    Der Report behauptete ihn trotzdem weiter als Tatsache. Ein Satz im
    Werkzeug wird geglaubt — er darf nicht mehr sagen als die Messung.
    """
    markdown = render_markdown(_run_with_one_failure())
    assert "zu freundlich" not in markdown
    assert "nicht **belegt**" in markdown or "nicht belegt" in markdown


def test_markdown_report_leads_with_the_average_not_the_pass_rate():
    """Die Quote streut um 27 %, der Mittelwert um 1,9 % (#41a, sechs Läufe).

    Wer nur die erste Kennzahl liest, soll die brauchbare lesen.
    """
    markdown = render_markdown(_run_with_one_failure())
    assert markdown.index("Ø Judge-Score") < markdown.index("Bestehensquote")


def test_the_pass_rate_is_marked_as_unstable():
    assert "instabil" in render_markdown(_run_with_one_failure())


def test_average_reports_how_many_cases_it_covers():
    """Ein Mittelwert ohne n lädt dazu ein, drei Fälle für eine Messung zu halten."""
    run = _run_with_one_failure()
    assert run.judged_count == 1
    assert "über 1 bewertete Fälle" in render_markdown(run)


def test_cases_just_below_the_threshold_are_named_as_such():
    # Zwei Traits mit 3 und 4 → Ø 3,5, also im Band, das an einem
    # Zehntelpunkt kippt.
    run = _run_with_average(
        "1: 3 | halb\n2: 4 | ja", expect_traits=("ist freundlich", "ist knapp")
    )
    assert run.near_threshold == 1
    markdown = render_markdown(run)
    assert "Band 3,0–3,9" in markdown  # deutsches Komma, der Satz ist Prosa
    assert "3.50 ~" in markdown


def test_a_run_without_borderline_cases_does_not_mention_the_band():
    run = _run_with_average("1: 5 | klar")
    assert run.near_threshold == 0
    assert "an einem Zehntelpunkt" not in render_markdown(run)


def test_a_run_without_judge_keeps_the_plain_result_line():
    run = EvalRun(model="chat-model", judge_model=None)
    run.results = run_persona_corpora([_persona_corpus()], lambda p, q: "x")
    markdown = render_markdown(run)
    assert run.average_score is None
    assert "Ergebnis:" in markdown
    assert "Ø Judge-Score" not in markdown


def test_markdown_report_shows_failing_answer_for_debugging():
    markdown = render_markdown(_run_with_one_failure())
    assert "Antworten der nicht bestandenen Fälle" in markdown
    assert "ist freundlich" in markdown


def test_markdown_report_without_judge_omits_the_bias_warning():
    run = EvalRun(model="chat-model", judge_model=None)
    run.results = run_persona_corpora([_persona_corpus()], lambda p, q: "x")
    assert "Judge-Bias" not in render_markdown(run)


def test_csv_report_has_stable_columns_for_run_comparison():
    csv_text = render_csv(_run_with_one_failure())
    header, first = csv_text.splitlines()[:2]
    assert header.split(",") == list(CSV_COLUMNS)
    assert first.startswith("persona:DORIS,DORIS,c1,0")


def test_new_csv_column_is_appended_so_older_reports_stay_comparable():
    columns = list(CSV_COLUMNS)
    assert columns[-1] == "near_threshold"
    assert columns[:-1] == [
        "group",
        "persona",
        "case_id",
        "passed",
        "average_score",
        "check_failures",
        "unscored_traits",
        "duration_ms",
        "error",
    ]


def test_csv_flags_the_borderline_cases():
    borderline = render_csv(
        _run_with_average(
            "1: 3 | halb\n2: 4 | ja", expect_traits=("ist freundlich", "ist knapp")
        )
    )
    assert borderline.splitlines()[1].endswith(",1")
    assert render_csv(_run_with_average("1: 5 | klar")).splitlines()[1].endswith(",0")


@pytest.mark.parametrize("passed_case", [True, False])
def test_run_ok_reflects_case_outcomes(passed_case):
    verdict_text = "1: 5 | ja" if passed_case else "1: 1 | nein"
    run = EvalRun(model="m", judge_model="m")
    run.results = run_persona_corpora(
        [_persona_corpus()], lambda p, q: "x", Judge(_FakeCore(verdict_text), "m")
    )
    assert run.ok is passed_case
