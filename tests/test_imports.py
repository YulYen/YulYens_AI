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


# ---- Startet die CLI überhaupt? (#64e) -------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SRC / "launch.py"), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_the_cli_lists_the_ensembles_as_a_real_process():
    """`--list-ensembles` von außen, nicht in-process.

    Die vorhandenen Tests rufen `_list_ensembles()` direkt auf und sehen
    deshalb nichts von dem, was beim *Start* schiefgehen kann: ein Importfehler
    im Argument-Parsing, eine kaputte `config.yaml`, ein Pfad, der nur relativ
    zum Repo-Wurzelverzeichnis stimmt. Genau diese Klasse Fehler bemerkt sonst
    erst der Nutzer.
    """
    result = _run_cli("--list-ensembles")
    assert result.returncode == 0, result.stderr
    assert "classic" in result.stdout
    assert "Traceback" not in result.stderr


def test_the_doctor_runs_through_without_a_backend():
    """`--doctor` muss auch ohne Ollama einen *Bericht* liefern.

    Der Rückgabewert darf 0 oder 1 sein — ohne laufendes Ollama ist „nicht
    ok" die richtige Antwort. Was nicht passieren darf, ist ein Stacktrace:
    ein Systemcheck, der selbst abstürzt, prüft nichts.
    """
    result = _run_cli("--doctor")
    assert result.returncode in (0, 1), (
        f"unerwarteter Exit-Code {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stdout.strip(), "der Doctor hat gar nichts berichtet"
