"""Report der Stoppuhr: Markdown zum Lesen, CSV zum Vergleichen (#42).

Dieselbe Arbeitsteilung wie bei der Eval-Suite (#41): das Markdown beantwortet
"wie war dieser Lauf", das CSV beantwortet "was hat sich seit dem letzten
geändert". Für einen Modellwechsel ist das zweite das eigentliche Artefakt.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from bench.harness import Aggregate, BenchRun, Sample, aggregate_by, measured

CSV_COLUMNS = (
    "mode",
    "model",
    "persona",
    "question_id",
    "repeat",
    "warmup",
    "t_first_ms",
    "t_total_ms",
    "chars",
    "chars_per_second",
    "t_model_first_ms",
    "holdback_ms",
    "tokens",
    "error",
)


def _ms(value: int | None) -> str:
    return "—" if value is None else f"{value} ms"


def _rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}".replace(".", ",")


def _seconds(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1000:.2f}".replace(".", ",") + " s"


def render_csv(run: BenchRun) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for sample in run.samples:
        rate = sample.chars_per_second
        writer.writerow(
            [
                run.mode,
                run.model,
                sample.persona,
                sample.question_id,
                sample.repeat,
                "1" if sample.warmup else "0",
                "" if sample.t_first_ms is None else sample.t_first_ms,
                sample.t_total_ms,
                sample.chars,
                "" if rate is None else f"{rate:.2f}",
                "" if sample.t_model_first_ms is None else sample.t_model_first_ms,
                "" if sample.holdback_ms is None else sample.holdback_ms,
                "" if sample.tokens is None else sample.tokens,
                sample.error or "",
            ]
        )
    return buffer.getvalue()


def _aggregate_table(rows: Sequence[Aggregate], header: str) -> list[str]:
    lines = [
        f"| {header} | Läufe | erstes Zeichen | Antwortdauer | Zeichen/s | Zeichen |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row.label} | {row.runs} | {_seconds(row.t_first_ms)} "
            f"| {_seconds(row.t_total_ms)} | {_rate(row.chars_per_second)} "
            f"| {row.chars if row.chars is not None else '—'} |"
        )
    return lines


def render_markdown(run: BenchRun) -> str:
    overall = run.overall
    lines: list[str] = ["# Perf-Report", ""]
    lines.append(f"- Lauf: `{run.started_at}`")
    lines.append(f"- Messpfad: `{run.mode}`")
    lines.append(f"- Backend / Modell: `{run.backend}` / `{run.model}`")
    lines.append(f"- Plan: {run.repeats} Runden, {run.warmup} Aufwärmrunde(n)")
    for name, value in run.settings:
        lines.append(f"- {name}: {value}")
    lines.append("")

    # Leitkennzahlen zuerst, und nur die zwei, die zwischen Läufen etwas
    # bedeuten. Dieselbe Lehre wie bei #41a: wer die instabile Zahl oben
    # hinschreibt, vergleicht später Münzwürfe.
    if overall.runs:
        lines.append(
            f"- **Erstes Zeichen: {_seconds(overall.t_first_ms)}** (Median über "
            f"{overall.runs} Messungen) — die Latenz, die jemand wirklich wartet"
        )
        lines.append(
            f"- **Durchsatz: {_rate(overall.chars_per_second)} Zeichen/s** "
            f"(Median) — die zweite Leitkennzahl"
        )
        if overall.holdback_ms is not None:
            share = ""
            if overall.t_first_ms:
                percent = round(100 * overall.holdback_ms / overall.t_first_ms)
                share = f", also {percent} % der wahrgenommenen Latenz"
            lines.append(
                f"- Davon **{_ms(overall.holdback_ms)} Guard-Holdback**{share}: "
                f"so lange lag das erste Token schon vor, ohne ausgeliefert zu "
                f"sein (#51). Eine Messung am Modell sieht diesen Anteil nicht"
            )
        lines.append(
            "- Die **Antwortdauer ist keine Vergleichszahl**: wie lange ein Lauf "
            "dauert, entscheidet vor allem, wie viel das Modell schreibt. Dafür "
            "steht Zeichen/s da"
        )
    else:
        lines.append("- **Keine verwertbare Messung** — siehe Fehler unten.")

    cold = run.cold_start
    if cold.runs and cold.t_first_ms is not None:
        lines.append(
            f"- Aufwärmrunde (nicht in den Zahlen oben): erstes Zeichen nach "
            f"{_seconds(cold.t_first_ms)}. Das ist der **Kaltstart nur dann**, "
            f"wenn das Modell vorher nicht schon im VRAM lag — nach einem Lauf "
            f"kurz davor hält `keep_alive` es dort, und die Zahl ist eine "
            f"gewöhnliche Messung"
        )
    lines.append("")

    for warning in run.warnings:
        lines.append(f"> ⚠️ {warning}")
    if run.warnings:
        lines.append("")

    usable = measured(run.samples)
    if usable:
        lines.append("## Nach Frage")
        lines.append("")
        lines.extend(
            _aggregate_table(aggregate_by(usable, lambda s: s.question_id), "Frage")
        )
        lines.append("")

        personas = {s.persona for s in usable}
        if len(personas) > 1:
            lines.append("## Nach Persona")
            lines.append("")
            lines.extend(
                _aggregate_table(aggregate_by(usable, lambda s: s.persona), "Persona")
            )
            lines.append("")

    if run.errors:
        lines.append("## Fehlgeschlagene Messungen")
        lines.append("")
        lines.append("| Persona | Frage | Runde | Fehler |")
        lines.append("| --- | --- | ---: | --- |")
        for sample in run.errors:
            lines.append(
                f"| {sample.persona} | {sample.question_id} | {sample.repeat} "
                f"| {sample.error} |"
            )
        lines.append("")

    lines.append(
        "Jede einzelne Messung steht in `report.csv` — zwei Läufe lassen sich "
        "dort zeilenweise gegeneinanderhalten."
    )
    lines.append("")
    return "\n".join(lines)


def render_console(run: BenchRun) -> str:
    """Die drei Zeilen, die nach dem Lauf im Terminal stehen sollen."""
    overall = run.overall
    if not overall.runs:
        return "Keine verwertbare Messung."
    parts = [
        (
            f"Erstes Zeichen: {_seconds(overall.t_first_ms)} "
            f"(Median, {overall.runs} Messungen)"
        ),
        f"Durchsatz:      {_rate(overall.chars_per_second)} Zeichen/s (Median)",
    ]
    if overall.holdback_ms is not None:
        parts.append(f"davon Holdback: {_ms(overall.holdback_ms)}")
    return "\n".join(parts)


def sample_line(sample: Sample) -> str:
    """Fortschrittszeile während des Laufs — der Lauf dauert Minuten."""
    tag = "aufwärmen" if sample.warmup else f"Runde {sample.repeat}"
    if not sample.ok:
        return f"  [{tag}] {sample.persona} {sample.question_id}: {sample.error}"
    first = "—" if sample.t_first_ms is None else f"{sample.t_first_ms} ms"
    return (
        f"  [{tag}] {sample.persona} {sample.question_id}: "
        f"erstes Zeichen {first}, {sample.chars} Zeichen "
        f"in {sample.t_total_ms} ms"
    )
