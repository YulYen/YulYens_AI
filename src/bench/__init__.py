"""Perf-Benchmark-Harness (#42): die Stoppuhr des Projekts.

Bewusst getrennt von der Eval-Suite (#41) — dort Qualität, hier Zeit. Die
Trennung ist keine Ordnungsliebe: ein Qualitätslauf darf einen Judge befragen
und Minuten kosten, ein Zeitlauf darf genau das nicht.

Gemessen wird die Zeit bis zum ersten **ausgelieferten** Zeichen, nicht bis zum
ersten Token des Modells. Warum das der Unterschied zwischen einer brauchbaren
und einer irreführenden Zahl ist, steht in ``bench/harness.py``.
"""

from bench.harness import (
    Aggregate,
    BenchAborted,
    BenchRun,
    Question,
    Sample,
    aggregate,
    aggregate_by,
    measure,
    measured,
    run_bench,
)

__all__ = [
    "Aggregate",
    "BenchAborted",
    "BenchRun",
    "Question",
    "Sample",
    "aggregate",
    "aggregate_by",
    "measure",
    "measured",
    "run_bench",
]
