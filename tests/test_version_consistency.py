"""Die Version steht an zwei Stellen — hier werden sie aneinander gebunden (#74).

`src/version.py` trägt die Zahl für die Laufzeit (`--version`, `--doctor`,
`/health`), `CHANGELOG.md` trägt sie als oberste Versionsüberschrift. Beide
werden von Hand gepflegt, und zwei Quellen für dieselbe Wahrheit laufen
auseinander, sobald nichts sie zusammenhält — die Lehre aus
`KNOWN_TOP_LEVEL_KEYS` (#66), das neben den pydantic-Modellen stand und
irgendwann etwas anderes behauptete als sie.

Der praktische Fall ist banal und würde genau deshalb passieren: die Konstante
hochziehen, den Changelog-Eintrag vergessen (oder umgekehrt). Danach meldet
`/health` eine Version, unter der im Changelog nichts steht.

**Der Git-Tag ist bewusst nicht Teil der Prüfung.** Er entsteht erst beim
Veröffentlichen, und die CI checkt flach aus — ein Test gegen `git describe`
wäre auf dem Runner entweder rot oder übersprungen, also wertlos. Die
Reihenfolge ist: beide Dateien stimmen überein, dann wird getaggt.

**Genau diese Lücke hat schon einmal zugeschlagen**, und der Test hier hätte
sie nicht schließen können: geplant war `v1.0.0` — den Tag gab es seit November
2025 bereits. Gesehen wurde er nicht, weil der Arbeits-Clone flach war und
`git tag` deshalb schwieg. Wer die Zahl anhebt, prüft **von Hand**, ob sie
frei ist (`git fetch --unshallow origin && git tag -l`); dieselbe Flachheit,
die den Test hier unmöglich macht, ist die Ursache des Fehlers.
"""

from __future__ import annotations

import re
from pathlib import Path

from version import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# `## [1.2.3] - 2026-08-05` — die Klammern sind Keep-a-Changelog-Konvention und
# tragen den Link ans Dateiende.
_RELEASE_HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _changelog() -> str:
    return CHANGELOG.read_text(encoding="utf-8")


def test_the_version_constant_is_a_semver_number():
    assert _SEMVER.match(__version__), (
        f"__version__ ist '{__version__}' — erwartet wird MAJOR.MINOR.PATCH. "
        "Vorabkennzeichnungen (-rc1) sind bewusst nicht vorgesehen: dieses "
        "Projekt hat einen Betreiber und keine Vorabverteilung."
    )


def test_the_newest_changelog_entry_matches_the_version_constant():
    versions = _RELEASE_HEADING.findall(_changelog())
    assert versions, (
        "CHANGELOG.md enthält keine Versionsüberschrift der Form "
        "'## [1.2.3] - JJJJ-MM-TT'."
    )
    assert versions[0] == __version__, (
        f"CHANGELOG.md führt zuletzt {versions[0]}, src/version.py sagt "
        f"{__version__}. Beim Anheben werden beide angefasst — sonst meldet "
        "/health eine Version, unter der im Changelog nichts steht."
    )


def test_released_versions_are_listed_newest_first():
    versions = [
        tuple(int(p) for p in v.split("."))
        for v in _RELEASE_HEADING.findall(_changelog())
    ]
    assert versions == sorted(versions, reverse=True), (
        "Die Versionsüberschriften stehen nicht absteigend. Neue Einträge "
        "kommen oben dazu — sonst zeigt die Prüfung oben auf die falsche Zeile."
    )


def test_the_changelog_keeps_a_section_for_unreleased_work():
    # Ohne diesen Abschnitt gibt es keinen Ort für die Zeile, die laut
    # CLAUDE.md in denselben PR gehört — und sie landete dann unter der
    # bereits veröffentlichten Version, die nicht mehr angefasst wird.
    assert "## [Unreleased]" in _changelog()
