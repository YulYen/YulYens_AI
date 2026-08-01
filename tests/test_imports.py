"""Jedes Paket muss sich als *erster* Projekt-Import laden lassen.

``import storage`` scheiterte, weil ``core/__init__.py`` den
``streaming_provider`` re-exportierte und der wiederum aus ``storage``
importiert:

    storage/__init__ → storage.store → core.utils → core/__init__
                     → core.streaming_provider → from storage import …

Es fiel nie auf, weil jeder bestehende Einstiegspunkt ``core`` zufällig zuerst
importiert — die Testsuite über ``conftest`` eingeschlossen. Genau deshalb
laufen diese Fälle in einem **frischen Subprozess**: in einem bereits
geladenen Interpreter ist der Zyklus unsichtbar.
"""

import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# Alle Pakete, die jemand von außen als Einstieg benutzen könnte — ein
# Wartungsskript gegen die Ablage, ein kleines CLI gegen den Guard, ein
# Migrationswerkzeug.
PACKAGES = [
    "storage",
    "auth",
    "core",
    "config.config_singleton",
    "security.tinyguard",
    "wiki.lookup",
    "api.provider",
    "ui.continuation",
]


@pytest.mark.parametrize("module", PACKAGES)
def test_module_imports_as_the_first_project_import(module):
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=SRC,
        capture_output=True,
        text=True,
    )

    assert (
        result.returncode == 0
    ), f"'import {module}' scheitert als erster Projekt-Import:\n{result.stderr}"
