"""CLI for the eval suite: ``python scripts/run_evals.py -e classic``.

Deliberately separate from launch.py — an eval run is a batch job, not the app,
and it must stay usable when the UI stack is broken. Exit code 1 when anything
failed, so it can gate a release.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from core.utils import resolve_model_name

from evals import corpus as corpus_mod
from evals.judge import Judge
from evals.report import render_csv, render_markdown
from evals.runner import (
    EvalRun,
    build_answer_fn,
    run_behaviour_corpora,
    run_guard_corpus,
    run_karl_corpus,
    run_persona_corpora,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_evals",
        description="Run the eval suite (golden questions, guard red-team).",
    )
    parser.add_argument("-c", "--config", help="Path to config.yaml.")
    parser.add_argument(
        "-e", "--ensemble", help="Persona ensemble to load (falls back to config)."
    )
    parser.add_argument(
        "--personas",
        help="Comma-separated persona filter, e.g. 'DORIS,PETER'.",
    )
    parser.add_argument(
        "--guard-only",
        action="store_true",
        help="Run only the guard red-team corpus (needs no model at all).",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip the LLM judge; only deterministic checks are evaluated.",
    )
    parser.add_argument(
        "--judge-model",
        help="Model for the judge (default: evals.judge_model, else the chat model).",
    )
    parser.add_argument(
        "--skip-karl",
        action="store_true",
        help="Skip the Karl summary corpus (one extra LLM run per case).",
    )
    parser.add_argument(
        "--out",
        help="Output directory for report.md / report.csv (default: logs/evals).",
    )
    return parser


def _build_summarize_fn(factory, cfg):
    """Wrap KarlSummarizer so the runner sees a plain history -> text callable."""
    from core.context_summarizer import KarlSummarizer

    ctx_cfg = dict(getattr(cfg, "context_management", {}) or {})
    karl_cfg = dict(ctx_cfg.get("karl", {}) or {})
    model_name = str(cfg.core.get("model_name", "unknown"))

    summarizer = KarlSummarizer(
        llm_core=factory.get_llm_core(),
        config=karl_cfg,
        chat_model_name=model_name,
        keep_alive=int(cfg.core.get("keep_alive", 600)),
    )

    def _summarize(history: list[dict]) -> str:
        # keep_last_messages would pass the tail through unchanged; the summary
        # itself is the leading system message Karl prepends.
        compressed = summarizer.summarize(history)
        for message in compressed:
            if message.get("role") == "system":
                return str(message.get("content", ""))
        return ""

    return _summarize


_PROTECTION_FLAGS = (
    "prompt_injection_protection",
    "pii_protection",
    "output_blocklist",
    "wrongdoing_protection",
)


def _guard_setup(cfg):
    """Build the guard exactly as configured, plus the set of disabled flags.

    Running the *configured* guard is the point: the report then answers "what
    does my setup actually block?", not "what could the guard block in theory".
    The disabled flags are handed to the runner so a switched-off protection is
    reported as skipped instead of counting as a failure.
    """
    from security.tinyguard import BasicGuard

    settings = dict(getattr(cfg, "security", {}) or {})
    flags = {name: bool(settings.get(name, True)) for name in _PROTECTION_FLAGS}
    disabled = frozenset(name for name, value in flags.items() if not value)

    def _make():
        # Fresh instance per case: the wrongdoing lock is session state.
        return BasicGuard(
            enabled=bool(settings.get("enabled", True)),
            prompt_injection_protection=flags["prompt_injection_protection"],
            pii_protection=flags["pii_protection"],
            output_blocklist=flags["output_blocklist"],
            wrongdoing_protection=flags["wrongdoing_protection"],
            wrongdoing_lock_turns=int(settings.get("wrongdoing_lock_turns", 0) or 0),
        )

    return _make, disabled


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from config.config_singleton import Config

    config_path = os.path.abspath(args.config or "config.yaml")
    cfg = Config(path=config_path)
    cfg.ensemble = args.ensemble or getattr(cfg, "ensemble", None)
    if not cfg.ensemble:
        parser.error(
            "Missing required parameter: --ensemble / -e "
            "(e.g. 'python scripts/run_evals.py -e classic')."
        )

    evals_cfg = dict(getattr(cfg, "evals", {}) or {})
    out_dir = Path(args.out or evals_cfg.get("out_dir") or "logs/evals")

    guard_corpus = corpus_mod.load_guard_corpus()
    guard_factory, disabled_protections = _guard_setup(cfg)
    guard_outcomes = run_guard_corpus(guard_corpus, guard_factory, disabled_protections)

    model_name = str(cfg.core.get("model_name", "unknown"))
    run = EvalRun(model=model_name, judge_model=None)
    run.guard_outcomes = list(guard_outcomes)

    if not args.guard_only:
        from core.factory import AppFactory

        factory = AppFactory()
        answer_fn = build_answer_fn(factory)

        judge = None
        if not args.no_judge:
            # Gleicher "same_as_chat"-Sentinel wie bei context_management.karl.model.
            judge_model = resolve_model_name(
                args.judge_model or evals_cfg.get("judge_model"), model_name
            )
            judge = Judge(
                llm_core=factory.get_llm_core(),
                model_name=judge_model,
                keep_alive=int(cfg.core.get("keep_alive", 600)),
            )
            run.judge_model = judge_model

        persona_corpora = corpus_mod.load_persona_corpora()
        if args.personas:
            wanted = {p.strip().upper() for p in args.personas.split(",") if p.strip()}
            persona_corpora = tuple(
                c for c in persona_corpora if c.persona.upper() in wanted
            )
            if not persona_corpora:
                parser.error(f"No persona corpus matches {sorted(wanted)}.")

        run.results.extend(run_persona_corpora(persona_corpora, answer_fn, judge))
        run.results.extend(
            run_behaviour_corpora(corpus_mod.load_behaviour_corpora(), answer_fn, judge)
        )
        if not args.skip_karl:
            run.results.extend(
                run_karl_corpus(
                    corpus_mod.load_karl_corpus(),
                    _build_summarize_fn(factory, cfg),
                    judge,
                )
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(render_markdown(run), encoding="utf-8")
    (out_dir / "report.csv").write_text(render_csv(run), encoding="utf-8")

    asserted = [o for o in run.guard_outcomes if not (o.known_gap or o.skipped)]
    print(
        f"Guard-Red-Team: {len(asserted) - run.guard_failed}/{len(asserted)} bestanden"
    )
    if run.guard_skipped:
        print(
            f"  {run.guard_skipped} Fälle übersprungen — Schutz in der Config aus: "
            f"{', '.join(sorted(disabled_protections))}"
        )
    if run.guard_known_gaps:
        print(f"  {run.guard_known_gaps} dokumentierte Lücke(n), siehe Report")
    if run.total:
        print(f"Fälle: {run.passed}/{run.total} bestanden, {run.errors} Fehler")
        if run.average_score is not None:
            print(f"Ø Judge-Score: {run.average_score:.2f}/5")
    print(f"Report: {out_dir / 'report.md'}")

    return 0 if run.ok else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
