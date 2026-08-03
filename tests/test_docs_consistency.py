"""Doku gegen die Wirklichkeit halten (#56-Nachtrag).

Anlass war ein Fehler, der genau so passiert ist: `make test` bekam beim
Browser-Rauchtest ein `not browser` dazu, die Doku behielt aber ihr altes
`pytest -q -m "not slow and not ollama"` samt der Zeile „entspricht: make
test". Wer sie kopierte, zog sich Playwright-Tests herein, die ohne
Browser-Build fehlschlagen. Aufgefallen ist das erst auf Nachfrage.

**Was hier geprüft wird, ist die mechanische Kopplung — nicht die Prosa.** Ob
ein Absatz noch stimmt, kann kein Test sagen; ob ein dokumentiertes Kommando
noch existiert, sehr wohl. Genau diese Klasse ist es, die still veraltet:
niemand liest die Testanleitung nach, während er den Makefile ändert.

Zwei Zusicherungen, beide in **beide** Richtungen wirksam — wie `known_gap` im
Guard-Korpus und die Allowlist des Audit-Jobs:

1. Jedes `pytest`-Kommando in der lebenden Doku ist eines, das der Makefile
   auch benutzt.
2. Jedes Makefile-Ziel steht in der Doku — oder ausdrücklich auf der
   Ausnahmeliste, mit Begründung.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = REPO_ROOT / "Makefile"

# Die Dateien, die den *aktuellen* Stand beschreiben. Datierte Berichte
# (`docs/framework_update_juni_2026.md`, `docs/modellwechsel_juni_2026.md`)
# gehören bewusst nicht dazu: sie halten fest, was damals galt, und ihre
# Kommandos mitzuziehen würde die Aufzeichnung fälschen.
LIVING_DOCS = (
    "README.md",
    "CONTRIBUTING.md",
    "docs/de/ReadMe.md",
    "docs/en/ReadMe.md",
    "docs/de/Features.md",
    "docs/en/Features.md",
    "evals/ReadMe.md",
)

# Ziele, die bewusst nicht in der Doku stehen. Ein Eintrag ist eine
# Entscheidung, kein Stummschalter — deshalb steht der Grund daneben.
UNDOCUMENTED_ON_PURPOSE = {
    "fix": "Bequemlichkeit über `make lint`; wer lintet, findet `--fix` selbst.",
    "clean": "Räumt Caches weg. Selbsterklärend und für niemanden eine Frage.",
    "run": "Startet die App; der Startbefehl steht ausführlicher in den ReadMes.",
}


def _text(relative: str) -> str:
    path = REPO_ROOT / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _living_text() -> str:
    return "\n".join(_text(name) for name in LIVING_DOCS)


def _make_targets() -> set[str]:
    return set(re.findall(r"^([a-z][a-z0-9-]*):", MAKEFILE.read_text(), re.MULTILINE))


def _marker_expressions(text: str) -> set[str]:
    """Alle `-m "…"`-Ausdrücke aus pytest-Aufrufen."""
    return set(re.findall(r'pytest[^\n]*?-m\s+"([^"]+)"', text))


# ---- Die Kommandos ---------------------------------------------------------


def test_documented_pytest_commands_exist_in_the_makefile():
    """Der Fehler, der den Test ausgelöst hat.

    Eine Doku-Zeile, die ein Kommando zeigt, das der Makefile so nicht mehr
    kennt, ist schlimmer als keine: sie sieht gepflegt aus.
    """
    documented = _marker_expressions(_living_text())
    known = _marker_expressions(MAKEFILE.read_text())

    unknown = sorted(documented - known)
    assert not unknown, (
        "Diese Marker-Ausdrücke stehen in der Doku, aber in keinem "
        f"Makefile-Ziel: {unknown}. Entweder ist der Makefile weitergezogen "
        "und die Doku hinterher — oder umgekehrt."
    )


def test_the_browser_marker_is_excluded_everywhere_it_matters():
    """Der Rauchtest braucht Playwright und einen Browser-Build.

    Er darf in keinem Kommando mitlaufen, das jemand nebenbei ausführt —
    weder im Makefile-Alltag noch in einer Doku-Zeile. Vergisst man das
    Gegenteil, schlägt es erst auf einem fremden Rechner fehl.
    """
    for expression in _marker_expressions(_living_text()) | _marker_expressions(
        MAKEFILE.read_text()
    ):
        if expression.strip() == "browser":
            continue  # das eine Ziel, das ihn absichtlich *nur* laufen lässt
        assert "not browser" in expression, (
            f'Der Ausdruck -m "{expression}" schließt den Browser-Rauchtest '
            "nicht aus."
        )


# ---- Die Ziele -------------------------------------------------------------


def test_every_make_target_is_documented_or_deliberately_not():
    """Ein Ziel, von dem niemand weiß, ist so gut wie keines."""
    documented = _living_text()
    missing = sorted(
        target
        for target in _make_targets()
        if target not in UNDOCUMENTED_ON_PURPOSE
        and not re.search(rf"make {re.escape(target)}\b", documented)
    )
    assert not missing, (
        f"Diese Makefile-Ziele stehen nirgends in der Doku: {missing}. "
        "Entweder dokumentieren — oder mit Begründung in "
        "UNDOCUMENTED_ON_PURPOSE aufnehmen."
    )


def test_the_exemption_list_carries_no_dead_entries():
    """Die Gegenrichtung: ein Ziel, das es nicht mehr gibt, muss raus.

    Sonst wächst die Liste still zu und deckt irgendwann etwas ab, worüber
    niemand mehr entschieden hat.
    """
    gone = sorted(set(UNDOCUMENTED_ON_PURPOSE) - _make_targets())
    assert not gone, (
        f"Diese Einträge in UNDOCUMENTED_ON_PURPOSE gibt es im Makefile nicht "
        f"(mehr): {gone}"
    )


@pytest.mark.parametrize("target,reason", sorted(UNDOCUMENTED_ON_PURPOSE.items()))
def test_each_exemption_states_why(target, reason):
    assert len(reason) > 30, f"{target} hat keine brauchbare Begründung"


# ---- Was die Doku über den Code behauptet ----------------------------------


def test_documented_marker_names_are_registered_in_pyproject():
    """Ein Marker, den pytest nicht kennt, ist ein Tippfehler mit Warnung."""
    config = _text("pyproject.toml")
    registered = set(re.findall(r'^\s*"([a-z_]+):', config, re.MULTILINE))
    used = set()
    for expression in _marker_expressions(_living_text()):
        used |= set(re.findall(r"[a-z_]+", expression)) - {"not", "and", "or"}

    unknown = sorted(used - registered)
    assert (
        not unknown
    ), f"Diese Marker stehen in der Doku, aber nicht in pyproject.toml: {unknown}"
