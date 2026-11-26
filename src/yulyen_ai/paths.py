"""Wo das Projekt auf der Platte liegt — eine Stelle statt `parents[n]` überall.

Config, Locales, Ensembles und Eval-Korpora liegen **neben** `src/`, nicht im
Paket. Das Paket wird deshalb nur editierbar installiert (`pip install -e .`)
und nie als Wheel verteilt: `__file__` zeigt dann in den Checkout, und
`PROJECT_ROOT` ist dessen Wurzel.

Vorher rechnete jedes Modul selbst nach oben (`parents[1]` in `launch.py`,
`parents[2]` in `config/`) — beim Umzug unter `src/yulyen_ai/` hätte jede
dieser Zahlen still auf `src/` statt auf die Wurzel gezeigt.

Importiert bewusst nichts aus dem Projekt: jede Schicht darf es lesen, ohne
einen Vertrag aus `[tool.importlinter]` zu verletzen.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENSEMBLES_DIR = PROJECT_ROOT / "ensembles"
LOCALES_DIR = PROJECT_ROOT / "locales"
EVALS_DIR = PROJECT_ROOT / "evals"
