"""CLI of the eval suite (#41).

The --guard-only path is the one that must work on any machine: no model, no
network, no gradio import. It is the reason the guard corpus can gate CI.
"""

import pytest
from config.config_singleton import Config

from evals.cli import main


@pytest.fixture(autouse=True)
def _clean_config():
    Config.reset_instance()
    yield
    Config.reset_instance()


def test_guard_only_run_writes_reports_and_exits_zero(tmp_path):
    out = tmp_path / "evals"
    code = main(["-e", "classic", "--guard-only", "--out", str(out)])

    assert code == 0
    markdown = (out / "report.md").read_text(encoding="utf-8")
    csv_text = (out / "report.csv").read_text(encoding="utf-8")
    assert "Guard-Red-Team" in markdown
    # No model ran, so there are no cases — only the CSV header.
    assert csv_text.strip().count("\n") == 0


# Die Lücken, die wir *bewusst* mitführen. Weder mehr noch weniger.
#
# Vorher stand hier „gar keine" — seit #50 war der Korpus lückenfrei. Diese eine
# ist eine bewusste Entscheidung: die Injection-Regel wirft einen harmlosen
# Artikel über `localhost` aus dem Kontext, und das ist gemessen, nicht vermutet.
# Sie zu verschweigen wäre bequemer, aber der Korpus soll die Wirklichkeit
# abbilden — sie ist das Abnahmekriterium für #62.
KNOWN_GAP_IDS = {"ctx_code_snippet_in_article_is_kept"}


def test_repo_corpus_carries_exactly_the_gaps_we_decided_on(tmp_path):
    """Nicht „keine Lücken", sondern „genau diese".

    Der Test schlägt in **beide** Richtungen an: eine neue Lücke verlangt eine
    bewusste Entscheidung, und eine geschlossene verlangt, das Flag zu
    entfernen. „Keine Lücken" hätte den zweiten Fall nie gemeldet.
    """
    from evals.corpus import load_guard_corpus

    gaps = {case.id for case in load_guard_corpus().cases if case.known_gap}
    assert gaps == KNOWN_GAP_IDS

    out = tmp_path / "evals"
    assert main(["-e", "classic", "--guard-only", "--out", str(out)]) == 0
    markdown = (out / "report.md").read_text(encoding="utf-8")
    for gap_id in KNOWN_GAP_IDS:
        assert gap_id in markdown, "eine bewusst mitgeführte Lücke fehlt im Report"


def test_known_gap_is_reported_but_does_not_fail_the_run(tmp_path, monkeypatch):
    """Der known_gap-Mechanismus selbst — an einem synthetischen Korpus.

    Bewusst nicht am Repo-Korpus: der soll gapfrei bleiben, und ein Test, der
    eine echte Lücke voraussetzt, würde beim Schließen kaputtgehen.
    """
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "guard_redteam.yaml").write_text(
        "cases:\n"
        "  - id: gap_case\n"
        "    stage: input\n"
        "    text: Diese Eingabe ist völlig harmlos\n"
        "    known_gap: true\n"
        "    note: Absichtlich unerfüllbar, prüft nur die Meldung.\n"
        "    expect:\n"
        "      ok: false\n"
        "      reason: prompt_injection\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("evals.corpus.EVALS_DIR", corpus_dir)

    out = tmp_path / "evals"
    # Exit-Code 0: eine dokumentierte Lücke ist gemeldet, aber kein Fehlschlag.
    assert main(["-e", "classic", "--guard-only", "--out", str(out)]) == 0
    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert "dokumentierte Lücken" in markdown
    assert "gap_case" in markdown


def test_full_run_against_the_dummy_backend_exercises_the_pipeline(tmp_path):
    """End-to-end over the real provider path, with the echo backend.

    The echo answers cannot satisfy the corpus, so the run must come back red —
    which is exactly what proves that answers, checks and report are wired up
    rather than silently skipped.
    """
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "include_date": False})
    cfg.override("wiki", {"mode": False})

    out = tmp_path / "evals"
    code = main(["-e", "classic", "--no-judge", "--skip-karl", "--out", str(out)])

    assert code == 1
    csv_lines = (out / "report.csv").read_text(encoding="utf-8").strip().splitlines()
    # Header plus one row per persona and behaviour case.
    assert len(csv_lines) > 10
    markdown = (out / "report.md").read_text(encoding="utf-8")
    assert "persona:DORIS" in markdown
    assert "behaviour:three_timestamps" in markdown
    # The echo answer must show up so a human can see why a case failed.
    assert "ECHO:" in markdown


def test_persona_filter_limits_the_run(tmp_path):
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "include_date": False})
    cfg.override("wiki", {"mode": False})

    out = tmp_path / "evals"
    main(
        [
            "-e",
            "classic",
            "--personas",
            "doris",  # lower case on purpose: the filter normalizes
            "--no-judge",
            "--skip-karl",
            "--out",
            str(out),
        ]
    )
    csv_text = (out / "report.csv").read_text(encoding="utf-8")
    assert "persona:DORIS" in csv_text
    assert "persona:PETER" not in csv_text


def test_judge_model_sentinel_resolves_to_the_chat_model(tmp_path, monkeypatch):
    """'same_as_chat' must not reach the model API as a literal name."""
    cfg = Config("config.yaml")
    cfg.ensemble = "classic"
    cfg.override("core", {"backend": "dummy", "include_date": False})
    cfg.override("wiki", {"mode": False})
    cfg.override("evals", {"judge_model": "same_as_chat"})

    seen = {}

    class _RecordingJudge:
        def __init__(self, llm_core, model_name, keep_alive=600):
            seen["model"] = model_name

        def score(self, *_args):
            from evals.judge import JudgeVerdict

            return JudgeVerdict(verdicts=(), raw="")

    monkeypatch.setattr("evals.cli.Judge", _RecordingJudge)
    main(
        [
            "-e",
            "classic",
            "--personas",
            "DORIS",
            "--skip-karl",
            "--out",
            str(tmp_path),
        ]
    )
    assert seen["model"] == cfg.core["model_name"]


def test_unknown_persona_filter_is_an_error(tmp_path):
    with pytest.raises(SystemExit):
        main(
            [
                "-e",
                "classic",
                "--personas",
                "NOBODY",
                "--no-judge",
                "--out",
                str(tmp_path),
            ]
        )


def test_missing_ensemble_is_an_error(tmp_path, monkeypatch):
    # Simulate a config without an `ensemble:` fallback key.
    monkeypatch.setattr(
        Config, "_load_config", _loader_without_ensemble(Config._load_config)
    )
    with pytest.raises(SystemExit):
        main(["--guard-only", "--out", str(tmp_path)])


def _loader_without_ensemble(original):
    def _patched(self, path):
        original(self, path)
        self.ensemble = None

    return _patched
