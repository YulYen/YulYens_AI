"""Report rendering: Markdown to read, CSV to diff between runs.

The CSV is the important one for #7: two runs (baseline vs. LoRA adapter) with
the same corpus produce two CSVs that can be compared row by row.
"""

from __future__ import annotations

import csv
import io

from evals.runner import EvalRun

CSV_COLUMNS = (
    "group",
    "persona",
    "case_id",
    "passed",
    "average_score",
    "check_failures",
    "unscored_traits",
    "duration_ms",
    "error",
)


def _fmt_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render_markdown(run: EvalRun) -> str:
    lines: list[str] = []
    lines.append("# Eval-Report")
    lines.append("")
    lines.append(f"- Lauf: `{run.started_at}`")
    lines.append(f"- Modell: `{run.model}`")
    lines.append(f"- Judge: `{run.judge_model or 'aus'}`")
    lines.append(
        f"- Ergebnis: **{run.passed}/{run.total}** Fälle bestanden, "
        f"{run.errors} Fehler, Ø Score {_fmt_score(run.average_score)}"
    )
    if run.guard_outcomes:
        asserted = len(run.guard_outcomes) - run.guard_known_gaps - run.guard_skipped
        lines.append(
            f"- Guard-Red-Team: **{asserted - run.guard_failed}/{asserted}** bestanden"
            + (
                f", {run.guard_skipped} übersprungen (Schutz aus)"
                if run.guard_skipped
                else ""
            )
            + (
                f", {run.guard_known_gaps} dokumentierte Lücke(n)"
                if run.guard_known_gaps
                else ""
            )
        )
    if run.judge_model:
        lines.append("")
        lines.append(
            "> Judge-Bias: bewertet dasselbe Modell seine eigenen Antworten, "
            "fallen die Scores zu freundlich aus. Absolute Zahlen sind nur im "
            "Vergleich zweier Läufe mit identischem Judge aussagekräftig."
        )
    lines.append("")

    if run.guard_failed:
        lines.append("## Guard-Red-Team: Fehlschläge")
        lines.append("")
        lines.append("| Fall | Stage | Abweichung |")
        lines.append("| --- | --- | --- |")
        for outcome in run.guard_outcomes:
            if not outcome.counts_as_failure:
                continue
            detail = "; ".join(outcome.failures)
            lines.append(f"| `{outcome.case_id}` | {outcome.stage} | {detail} |")
        lines.append("")

    if run.guard_skipped:
        lines.append("## Guard-Red-Team: übersprungen")
        lines.append("")
        lines.append(
            "Diese Angriffe kämen durch — aber nur, weil der zuständige Schutz "
            "in `config.yaml` ausgeschaltet ist. Kein Guard-Fehler, wohl aber "
            "eine Aussage über das laufende Setup."
        )
        lines.append("")
        for outcome in run.guard_outcomes:
            if not outcome.skipped:
                continue
            lines.append(
                f"- `{outcome.case_id}` — braucht "
                f"`security.{outcome.skipped_protection}: true`"
            )
        lines.append("")

    if run.guard_known_gaps:
        lines.append("## Guard-Red-Team: dokumentierte Lücken")
        lines.append("")
        lines.append(
            "Bewusst akzeptiert, zählt nicht als Fehlschlag — schlägt der Fall "
            "eines Tages durch, verliert er sein `known_gap`-Flag."
        )
        lines.append("")
        for outcome in run.guard_outcomes:
            if not (outcome.known_gap and not outcome.passed):
                continue
            lines.append(f"- `{outcome.case_id}` — {outcome.note}")
        lines.append("")

    lines.append("## Fälle")
    lines.append("")
    lines.append("| Gruppe | Fall | Status | Ø Score | Anmerkung |")
    lines.append("| --- | --- | --- | --- | --- |")
    for result in run.results:
        if result.error:
            status, note = "🔥 Fehler", result.error
        elif not result.checks_passed:
            status = "❌ Check"
            note = "; ".join(f"{f.kind}: {f.detail}" for f in result.check_failures)
        elif not result.traits_passed:
            status = "⚠️ Charakter"
            note = "; ".join(
                f"{v.score}/5 — {v.trait}"
                for v in (result.verdict.verdicts if result.verdict else ())
                if not v.passed
            )
        else:
            status, note = "✅", ""
        score = _fmt_score(result.verdict.average if result.verdict else None)
        lines.append(
            f"| {result.group} | `{result.case_id}` | {status} | {score} "
            f"| {note.replace('|', '/')} |"
        )
    lines.append("")

    failed = [r for r in run.results if not r.passed]
    if failed:
        lines.append("## Antworten der nicht bestandenen Fälle")
        lines.append("")
        for result in failed:
            lines.append(f"### {result.group} / `{result.case_id}`")
            lines.append("")
            lines.append(f"**Frage:** {result.question}")
            lines.append("")
            lines.append(f"**Antwort:** {result.answer or '—'}")
            lines.append("")
            for verdict in result.verdict.verdicts if result.verdict else ():
                mark = "✅" if verdict.passed else "❌"
                score = verdict.score if verdict.score is not None else "—"
                lines.append(f"- {mark} {score}/5 — {verdict.trait} ({verdict.reason})")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(run: EvalRun) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for result in run.results:
        writer.writerow(
            [
                result.group,
                result.persona,
                result.case_id,
                int(result.passed),
                "" if not result.verdict else result.verdict.average or "",
                "; ".join(f"{f.kind}: {f.detail}" for f in result.check_failures),
                "; ".join(result.verdict.unscored) if result.verdict else "",
                result.duration_ms,
                result.error or "",
            ]
        )
    return buffer.getvalue()
