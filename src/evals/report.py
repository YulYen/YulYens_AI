"""Report rendering: Markdown to read, CSV to diff between runs.

The CSV is the important one for #7: two runs (baseline vs. LoRA adapter) with
the same corpus produce two CSVs that can be compared row by row.
"""

from __future__ import annotations

import csv
import io

from evals.runner import (
    NEAR_THRESHOLD_HIGH,
    NEAR_THRESHOLD_LOW,
    EvalRun,
    is_near_threshold,
)

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
    # Angehängt, nicht einsortiert: ältere Reports bleiben so spaltenweise
    # vergleichbar mit neuen.
    "near_threshold",
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
    # Leitkennzahl zuerst, Bestehensquote danach — nicht umgekehrt (#41a).
    # Sechs Läufe mit identischem Code ergaben 3 bis 6 bestandene Fälle von 17
    # (27 % relative Streuung), aber Ø 3,57 bis 3,79 (1,9 %). Wer den Adapter
    # aus #7 gegen die Baseline über die Quote vergleicht, misst Münzwürfe.
    if run.average_score is not None:
        lines.append(
            f"- **Ø Judge-Score {_fmt_score(run.average_score)}/5** "
            f"(über {run.judged_count} bewertete Fälle) — die Leitkennzahl "
            f"für den Vergleich zweier Läufe"
        )
        lines.append(
            f"- Bestehensquote: {run.passed}/{run.total} Fälle, "
            f"{run.errors} Fehler. **Zwischen Läufen instabil** und deshalb "
            f"kein Vergleichsmaß zwischen zwei Codeständen"
        )
        if run.near_threshold:
            # Bandgrenzen aus den Konstanten, aber mit deutschem Dezimalkomma —
            # der Rest des Satzes ist Prosa, nicht Tabelle.
            low = f"{NEAR_THRESHOLD_LOW:.1f}".replace(".", ",")
            high = f"{NEAR_THRESHOLD_HIGH - 0.1:.1f}".replace(".", ",")
            lines.append(
                f"- Davon **{run.near_threshold} Fälle im Band {low}–{high}** — "
                f"sie entscheiden sich an einem Zehntelpunkt an der Schwelle "
                f"(4 besteht, 3 nicht) und kippen beim nächsten Lauf womöglich "
                f"von allein. In der Tabelle mit ~ markiert"
            )
    else:
        lines.append(
            f"- Ergebnis: **{run.passed}/{run.total}** Fälle bestanden, "
            f"{run.errors} Fehler (kein Judge — nur deterministische Checks)"
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
        # Hier stand bis #41a, ein sich selbst bewertendes Modell falle "zu
        # freundlich" aus. Genau das wurde gemessen und *nicht* bestätigt: ein
        # fremder Judge (qwen2.5:7b statt ministral-3:8b) lieferte Ø 3,71 und
        # lag damit mitten in der Spanne der Selbstbewertungen. Ein Satz, der
        # im Werkzeug steht, wird geglaubt — er darf deshalb nicht mehr
        # behaupten als die Messung hergibt.
        lines.append(
            "> Judge-Bias: gemessen (#41a) ist er für dieses Paar **nicht "
            "belegt** — ein fremder Judge lag mitten in der Spanne der "
            "Selbstbewertungen. Für einen deutlich stärkeren Judge bleibt er "
            "plausibel und ungemessen. Absolute Zahlen sind so oder so nur im "
            "Vergleich zweier Läufe mit identischem Judge aussagekräftig."
        )
    if run.warnings:
        lines.append("")
        for warning in run.warnings:
            lines.append(f"> ⚠️ {warning}")
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
        average = result.verdict.average if result.verdict else None
        # "~" macht die Fälle sichtbar, die beim nächsten Lauf von allein
        # kippen können — sonst liest man einen Wechsel als Wirkung.
        score = _fmt_score(average) + (" ~" if is_near_threshold(average) else "")
        # Pipes escapen, nicht ersetzen: in der Anmerkung steht bei einem
        # fehlgeschlagenen `must_match` der Regex im Klartext, und dort ist `|`
        # die Alternative. Das frühere `.replace("|", "/")` machte aus dem
        # korrekten `(ki|programm|…)` ein `(ki/programm/…)` — ein Muster, das so
        # nie zutreffen könnte. Wer den Report liest, sucht dann einen Fehler
        # im Korpus, den es nicht gibt (genau das ist beim Baseline-Lauf
        # passiert). `\|` hält die Markdown-Tabelle heil und den Regex lesbar.
        # Die Ersetzung steht bewusst außerhalb des f-Strings: Backslashes in
        # f-String-Ausdrücken sind erst ab Python 3.12 erlaubt, das Projekt
        # sagt 3.10+.
        safe_note = note.replace("|", "\\|")
        lines.append(
            f"| {result.group} | `{result.case_id}` | {status} | {score} "
            f"| {safe_note} |"
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
                score = "—" if verdict.score is None else f"{verdict.score}"
                lines.append(f"- {mark} {score}/5 — {verdict.trait} ({verdict.reason})")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(run: EvalRun) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for result in run.results:
        average = result.verdict.average if result.verdict else None
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
                int(is_near_threshold(average)),
            ]
        )
    return buffer.getvalue()
