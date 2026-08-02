"""Der Abgleich zwischen pip-audit und den bewusst getragenen Befunden (#61).

Geprüft wird die Vergleichslogik, nicht pip-audit selbst — der Aufruf geht ins
Netz und gehört nicht in die Suite. Dass die ausgelieferte Liste zum echten
Stand passt, sagt der CI-Job.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from audit_deps import (  # noqa: E402
    DEFAULT_ALLOWLIST,
    Finding,
    compare,
    findings_from_report,
    load_allowlist,
    render,
)


def _report(*vulns):
    """pip-audit-JSON in der Form, die der echte Aufruf liefert."""
    return {
        "dependencies": [
            {"name": name, "version": version, "vulns": [{"id": i, "fix_versions": f}]}
            for name, version, i, f in vulns
        ]
    }


def test_a_finding_that_is_carried_on_purpose_is_not_a_failure():
    findings = findings_from_report(_report(("gradio", "5.50.0", "PYSEC-1", ["6.6.0"])))
    result = compare(findings, {"PYSEC-1": "Grund"})
    assert result.ok
    assert [f.vuln_id for f in result.carried] == ["PYSEC-1"]


def test_a_new_finding_turns_the_job_red():
    """Der eigentliche Zweck: etwas Unbekanntes braucht eine Entscheidung."""
    findings = findings_from_report(_report(("pillow", "11.3.0", "PYSEC-NEU", [])))
    result = compare(findings, {"PYSEC-1": "Grund"})
    assert not result.ok
    assert [f.vuln_id for f in result.unexpected] == ["PYSEC-NEU"]


def test_an_entry_that_is_no_longer_reported_also_turns_it_red():
    """Die Gegenrichtung — sonst wächst die Liste still zu.

    Genau dieselbe Logik wie bei `known_gap` im Guard-Korpus: ein bloßes
    „keine neuen Befunde" würde nie melden, dass eine Altlast erledigt ist.
    """
    result = compare([], {"PYSEC-ERLEDIGT": "Grund"})
    assert not result.ok
    assert result.stale == ["PYSEC-ERLEDIGT"]


def test_the_same_id_on_several_paths_is_one_decision():
    """pip-audit meldet eine ID mehrfach, wenn ein Paket mehrfach im Baum hängt."""
    report = {
        "dependencies": [
            {"name": "pillow", "version": "11.3.0", "vulns": [{"id": "PYSEC-1"}]},
            {"name": "pillow", "version": "11.3.0", "vulns": [{"id": "PYSEC-1"}]},
        ]
    }
    assert [f.vuln_id for f in findings_from_report(report)] == ["PYSEC-1"]


def test_a_clean_report_against_an_empty_list_is_green():
    assert compare([], {}).ok


def test_a_duplicated_id_in_the_allowlist_is_an_error(tmp_path):
    """Zwei Einträge für denselben Befund heißt: zwei Begründungen, eine gilt."""
    path = tmp_path / "allow.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "groups": [
                    {"package": "a", "reason": "r1", "ids": ["PYSEC-1"]},
                    {"package": "b", "reason": "r2", "ids": ["PYSEC-1"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="PYSEC-1"):
        load_allowlist(path)


def test_the_output_names_what_to_do_about_a_new_finding():
    text = render(compare([Finding("PYSEC-NEU", "pillow", "11.3.0", ())], {}))
    assert "PYSEC-NEU" in text
    assert "audit_allowlist.yaml" in text
    assert "keine Fassung" in text


# ---- Die ausgelieferte Liste ---------------------------------------------


def test_the_shipped_allowlist_is_readable_and_gives_every_entry_a_reason():
    """Ein Eintrag ohne Begründung ist ein Stummschalter, kein Beschluss."""
    reasons = load_allowlist(DEFAULT_ALLOWLIST)
    assert reasons, "die ausgelieferte Liste ist leer"
    for vuln_id, reason in reasons.items():
        assert len(reason) > 40, f"{vuln_id} hat keine brauchbare Begründung"
        assert reason.startswith("["), f"{vuln_id} nennt kein Paket"
