"""Wo das Projekt auf der Platte liegt — eine Stelle statt `parents[n]` überall.

Config, Locales und Ensembles liegen **neben** `src/`, nicht im
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


class NotACheckoutError(RuntimeError):
    """Das Paket liegt nicht in einem Checkout — meist ein `pip install .`."""


def checkout_root(package_file: str | Path) -> Path:
    """Die Wurzel des Checkouts, in dem `package_file` liegt — oder ein lauter Fehler.

    Ohne diese Prüfung zeigte ein versehentliches `pip install .` (ohne `-e`)
    still nach `site-packages`: kein Absturz beim Import, sondern fehlende
    Ensembles und Locales irgendwo mitten im Start.
    """
    root = Path(package_file).resolve().parents[2]
    if not (root / "ensembles").is_dir() or not (root / "locales").is_dir():
        raise NotACheckoutError(
            f"yulyen_ai liegt unter {Path(package_file).resolve().parent}, aber "
            f"{root} ist kein Checkout (ensembles/ und locales/ fehlen). "
            "Das Paket wird nur editierbar installiert: im Repo "
            "'pip install -e .' ausführen."
        )
    return root


PROJECT_ROOT = checkout_root(__file__)
ENSEMBLES_DIR = PROJECT_ROOT / "ensembles"
LOCALES_DIR = PROJECT_ROOT / "locales"
