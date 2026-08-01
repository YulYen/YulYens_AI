"""Corpus loading and validation (#41).

The strictness is the point: a corpus with a typo'd key would silently drop
half its expectations, so the loader must reject it loudly.
"""

import pytest

from evals.corpus import (
    CorpusError,
    load_behaviour_corpora,
    load_guard_corpus,
    load_karl_corpus,
    load_persona_corpora,
)

# ---- The corpora shipped in the repo --------------------------------------


def test_repo_persona_corpora_load_and_cover_the_classic_four():
    corpora = load_persona_corpora()
    personas = {c.persona for c in corpora}
    assert personas == {"LEAH", "DORIS", "PETER", "POPCORN"}
    for corpus in corpora:
        assert corpus.cases, f"{corpus.source} has no cases"
        for case in corpus.cases:
            # Every case must be judgeable or checkable, never neither.
            assert case.expect_traits or not case.checks.is_empty()


def test_repo_behaviour_corpora_load():
    corpora = load_behaviour_corpora()
    names = {c.name for c in corpora}
    assert "three_timestamps" in names


def test_repo_guard_corpus_loads_with_notes_on_gaps():
    corpus = load_guard_corpus()
    assert corpus.cases
    for case in corpus.cases:
        if case.known_gap:
            assert case.note, f"{case.id} is a known gap but carries no note"


def test_repo_karl_corpus_loads():
    corpus = load_karl_corpus()
    assert corpus is not None
    assert corpus.cases
    for case in corpus.cases:
        assert case.history


# ---- Validation ----------------------------------------------------------


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_unknown_key_in_case_is_rejected(tmp_path):
    _write(
        tmp_path,
        "personas/x.yaml",
        "persona: X\ncases:\n  - id: a\n    question: q\n    expct_traits: [t]\n",
    )
    with pytest.raises(CorpusError, match="unknown key"):
        load_persona_corpora(tmp_path)


def test_case_without_any_expectation_is_rejected(tmp_path):
    _write(
        tmp_path, "personas/x.yaml", "persona: X\ncases:\n  - id: a\n    question: q\n"
    )
    with pytest.raises(CorpusError, match="at least one"):
        load_persona_corpora(tmp_path)


def test_duplicate_case_id_is_rejected(tmp_path):
    _write(
        tmp_path,
        "personas/x.yaml",
        "persona: X\ncases:\n"
        "  - id: a\n    question: q\n    expect_traits: [t]\n"
        "  - id: a\n    question: q2\n    expect_traits: [t]\n",
    )
    with pytest.raises(CorpusError, match="duplicate case id"):
        load_persona_corpora(tmp_path)


def test_broken_regex_is_rejected_at_load_time(tmp_path):
    _write(
        tmp_path,
        "personas/x.yaml",
        "persona: X\ncases:\n  - id: a\n    question: q\n"
        "    checks:\n      must_match: ['[unclosed']\n",
    )
    with pytest.raises(CorpusError, match="not a valid regex"):
        load_persona_corpora(tmp_path)


def test_placeholder_in_pattern_survives_validation(tmp_path):
    _write(
        tmp_path,
        "personas/x.yaml",
        "persona: X\ncases:\n  - id: a\n    question: q\n"
        "    checks:\n      must_match: ['{today_iso}']\n",
    )
    corpora = load_persona_corpora(tmp_path)
    assert corpora[0].cases[0].checks.must_match == ("{today_iso}",)


def test_two_corpora_for_the_same_persona_are_rejected(tmp_path):
    body = "cases:\n  - id: a\n    question: q\n    expect_traits: [t]\n"
    _write(tmp_path, "personas/one.yaml", f"persona: X\n{body}")
    _write(tmp_path, "personas/two.yaml", f"persona: X\n{body}")
    with pytest.raises(CorpusError, match="more than one corpus file"):
        load_persona_corpora(tmp_path)


def test_min_chars_above_max_chars_is_rejected(tmp_path):
    _write(
        tmp_path,
        "personas/x.yaml",
        "persona: X\ncases:\n  - id: a\n    question: q\n"
        "    checks:\n      max_chars: 10\n      min_chars: 20\n",
    )
    with pytest.raises(CorpusError, match="must not exceed"):
        load_persona_corpora(tmp_path)


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


def test_missing_behaviour_directory_yields_empty_tuple(tmp_path):
    assert load_behaviour_corpora(tmp_path) == ()


def test_missing_karl_corpus_yields_none(tmp_path):
    assert load_karl_corpus(tmp_path) is None


def test_karl_case_rejects_unknown_role(tmp_path):
    _write(
        tmp_path,
        "karl_summary.yaml",
        "name: k\ncases:\n  - id: a\n    history:\n"
        "      - role: narrator\n        content: hi\n    expect_traits: [t]\n",
    )
    with pytest.raises(CorpusError, match="must be user, assistant or system"):
        load_karl_corpus(tmp_path)


def test_invalid_yaml_names_the_file(tmp_path):
    _write(tmp_path, "personas/x.yaml", "persona: [unclosed\n")
    with pytest.raises(CorpusError, match="invalid YAML"):
        load_persona_corpora(tmp_path)
