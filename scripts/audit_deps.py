#!/usr/bin/env python3
"""pip-audit mit Gedächtnis: rot nur bei *neuen* Befunden (#61).

Ein Audit-Job, der wegen nicht behebbarer Befunde dauerhaft rot steht, wird
binnen zwei Wochen ignoriert — dann ist er schlimmer als keiner, weil er die
Farbe entwertet. Der erste Anlauf hier war genau das: `continue-on-error`
verhindert zwar, dass der Workflow fehlschlägt, aber die Kachel am PR bleibt
rot.

Deshalb dasselbe Muster wie beim `known_gap` im Guard-Korpus: die bewusst
getragenen Befunde stehen mit Begründung in `audit_allowlist.yaml`, und der
Abgleich schlägt in **beide** Richtungen an. Ein neuer Befund ist rot, weil er
eine Entscheidung braucht. Ein Eintrag, den pip-audit nicht mehr meldet, ist
ebenfalls rot — sonst bliebe er für immer stehen, und die Liste schützte
irgendwann nichts mehr.

    python scripts/audit_deps.py                 # löst auf und prüft
    python scripts/audit_deps.py --report r.json # vorhandenen Report prüfen
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ALLOWLIST = REPO_ROOT / "audit_allowlist.yaml"
DEFAULT_REQUIREMENTS = REPO_ROOT / "requirements.txt"


@dataclass(frozen=True)
class Finding:
    vuln_id: str
    package: str
    version: str
    fix_versions: tuple[str, ...] = ()

    @property
    def fix_hint(self) -> str:
        return ", ".join(self.fix_versions) if self.fix_versions else "keine Fassung"


@dataclass
class Comparison:
    """Was pip-audit meldet, gegen das, was wir bewusst tragen."""

    unexpected: list[Finding] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    carried: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unexpected and not self.stale


def load_allowlist(path: Path) -> dict[str, str]:
    """ID -> Begründung. Eine doppelt geführte ID ist ein Fehler, kein Detail."""
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    reasons: dict[str, str] = {}
    for group in data.get("groups") or []:
        package = str(group.get("package") or "?")
        reason = " ".join(str(group.get("reason") or "").split())
        for vuln_id in group.get("ids") or []:
            key = str(vuln_id)
            if key in reasons:
                raise SystemExit(f"{path.name}: {key} steht doppelt in der Liste")
            reasons[key] = f"[{package}] {reason}"
    return reasons


def findings_from_report(report: dict) -> list[Finding]:
    """Die Befunde aus einem pip-audit-JSON — je ID nur einmal.

    pip-audit listet dieselbe ID mehrfach, wenn ein Paket über mehrere Wege in
    den Baum kommt. Für die Entscheidung „tragen wir das?" ist das eine Frage,
    nicht drei.
    """
    seen: dict[str, Finding] = {}
    for dep in report.get("dependencies") or []:
        for vuln in dep.get("vulns") or []:
            finding = Finding(
                vuln_id=str(vuln.get("id")),
                package=str(dep.get("name")),
                version=str(dep.get("version")),
                fix_versions=tuple(vuln.get("fix_versions") or ()),
            )
            seen.setdefault(finding.vuln_id, finding)
    return sorted(seen.values(), key=lambda f: (f.package, f.vuln_id))


def compare(findings: list[Finding], allowed: dict[str, str]) -> Comparison:
    found_ids = {f.vuln_id for f in findings}
    return Comparison(
        unexpected=[f for f in findings if f.vuln_id not in allowed],
        stale=sorted(set(allowed) - found_ids),
        carried=[f for f in findings if f.vuln_id in allowed],
    )


def run_pip_audit(requirements: Path) -> dict:
    """pip-audit aufrufen. Exit-Code 1 heißt „Befunde", nicht „kaputt"."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip_audit",
            "-r",
            str(requirements),
            "--progress-spinner",
            "off",
            "-f",
            "json",
        ],
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"pip-audit lieferte keinen Report (exit {proc.returncode})")
    return json.loads(proc.stdout)


def render(comparison: Comparison) -> str:
    lines: list[str] = []
    if comparison.carried:
        lines.append(f"Bewusst getragen: {len(comparison.carried)} Befund(e)")
        for finding in comparison.carried:
            lines.append(
                f"  · {finding.package} {finding.version} — {finding.vuln_id} "
                f"(behoben in: {finding.fix_hint})"
            )
        lines.append("")

    if comparison.unexpected:
        lines.append(
            f"NEU — nicht in audit_allowlist.yaml ({len(comparison.unexpected)}):"
        )
        for finding in comparison.unexpected:
            lines.append(
                f"  ✗ {finding.package} {finding.version} — {finding.vuln_id} "
                f"(behoben in: {finding.fix_hint})"
            )
        lines.append("")
        lines.append(
            "Entscheiden: Abhängigkeit heben — oder den Befund mit Begründung "
            "in audit_allowlist.yaml aufnehmen."
        )
        lines.append("")

    if comparison.stale:
        lines.append(
            f"ERLEDIGT — steht noch in audit_allowlist.yaml ({len(comparison.stale)}):"
        )
        for vuln_id in comparison.stale:
            lines.append(f"  ✗ {vuln_id}")
        lines.append("")
        lines.append(
            "pip-audit meldet diese Befunde nicht mehr. Eintrag entfernen, "
            "sonst trägt die Liste bald Altlasten statt Entscheidungen."
        )
        lines.append("")

    if comparison.ok:
        lines.append("Keine neuen Befunde, keine Altlasten in der Liste.")
    return "\n".join(lines).rstrip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="audit_deps",
        description="pip-audit gegen die bewusst getragenen Befunde halten.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Vorhandenes pip-audit-JSON prüfen (statt selbst laufen).",
    )
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--requirements", type=Path, default=DEFAULT_REQUIREMENTS)
    args = parser.parse_args(argv)

    allowed = load_allowlist(args.allowlist)
    report = (
        json.loads(args.report.read_text(encoding="utf-8"))
        if args.report
        else run_pip_audit(args.requirements)
    )

    comparison = compare(findings_from_report(report), allowed)
    print(render(comparison))
    return 0 if comparison.ok else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    sys.exit(main())
