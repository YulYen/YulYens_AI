"""Geparkte Live-Tests für den Modellwechsel auf 16 GB VRAM (#78).

Diese Tests sind absichtlich **ausgeschaltet**. Sie beschreiben, was ein Modell
der 14B-Klasse (geplant: `ministral-3:14b`) können sollte, das heutige
`ministral-3:8b` aber nicht — am 2026-11-02 gemessen: 0 von 5 bei beiden
Tests. Sie werden aktiviert, wenn der Default in `config.yaml` auf das größere
Modell wechselt — vorher kalibrieren, siehe #78 in `backlog.md`.

Von Hand einschalten, ein Modell pro Lauf, mit Logdatei (PowerShell, braucht
Ollama)::

    $env:YULYEN_14B_TESTS = "1"
    $env:YULYEN_TEST_MODEL = "leo-hessianai-13b-chat.Q5:latest"
    python -m pytest tests/test_ai_via_api_14b.py -rA | Tee-Object logs/14b_leo13b.txt

`YULYEN_TEST_MODEL` (aus `tests/conftest.py`) ersetzt das Modell aus der
Config; ohne ihn läuft der Default. `-rA` zeigt die Antwort des Modells auch
bei bestandenen Tests. Mehrere Läufe: die letzte Zeile in `1..5 | % { … }`
fassen und `Tee-Object -Append` nehmen. Danach beide Variablen mit
`Remove-Item Env:YULYEN_14B_TESTS, Env:YULYEN_TEST_MODEL` wieder entfernen.

Warum gerade diese Aufgaben: In Mistrals eigener Tabelle (Ministral-3-Paper,
arXiv 2601.08584) trennt einfacher Code die beiden Größen kaum (MBPP 70,0 gegen
71,6), Faktenwissen dagegen deutlich (TriviaQA 68,1 gegen 74,9). Beide Tests
setzen deshalb auf *Wissen plus einen Denkschritt* statt auf reine
Rechen- oder Programmierfleißarbeit.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata

import pytest

_WARTET_AUF_14B = pytest.mark.skipif(
    os.environ.get("YULYEN_14B_TESTS") != "1",
    reason=(
        "Wartet auf den Modellwechsel (#78): ministral-3:8b schafft das "
        "nicht, ministral-3:14b auf 16 GB VRAM hoffentlich. Von Hand mit "
        "YULYEN_14B_TESTS=1, siehe Modul-Docstring."
    ),
)


def _frage(client, frage: str, persona: str = "PETER") -> str:
    response = client.post("/ask", json={"question": frage, "persona": persona})
    assert response.status_code == 200, response.text[:500]
    antwort = response.json().get("answer", "")
    # Für -rA: beim Kalibrieren zählt auch, *wie* ein bestandener Lauf aussah.
    print(f"--- Antwort ---\n{antwort}")
    return antwort


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


# ---- 1. Coding: PETER schreibt Code, der wirklich läuft ------------------------

_RUNDEN_AUFGABE = (
    "Schreibe eine Python-Funktion runde_kaufmaennisch(betrag: str, stellen: int)"
    " -> str. Sie bekommt einen Geldbetrag als Dezimal-String und rundet ihn"
    " kaufmännisch auf `stellen` Nachkommastellen: genau halbe Werte immer vom"
    " Nullpunkt weg. Rückgabe als String mit genau `stellen` Nachkommastellen."
    ' Beispiele: runde_kaufmaennisch("2.675", 2) == "2.68" und'
    ' runde_kaufmaennisch("-2.5", 0) == "-3". Nur Standardbibliothek. Antworte nur'
    " mit dem Code in einem Python-Codeblock."
)

# (Betrag, Stellen, erwartet) — jeder Fall fängt mindestens einen typischen Fehler:
# round() rundet zur geraden Zahl, float kennt 2.675 und 1.005 nicht genau,
# floor(x + 0.5) rundet negative Werte zur Null hin.
_RUNDEN_FAELLE = [
    ("2.675", 2, "2.68"),
    ("1.005", 2, "1.01"),
    ("0.125", 2, "0.13"),
    ("2.5", 0, "3"),
    ("-2.5", 0, "-3"),
    ("-0.125", 2, "-0.13"),
    ("19.995", 2, "20.00"),
    ("7", 2, "7.00"),
]

_HARNISCH = """

import json as _json
import sys as _sys

_faelle = _json.loads(_sys.argv[1])
print(_json.dumps([str(runde_kaufmaennisch(b, s)) for b, s in _faelle]))
"""


def _code_aus_antwort(antwort: str) -> str:
    bloecke = re.findall(r"```[a-zA-Z]*\s*\n(.*?)```", antwort, flags=re.DOTALL)
    for block in bloecke:
        if "def runde_kaufmaennisch" in block:
            return block
    return antwort if "def runde_kaufmaennisch" in antwort else ""


@_WARTET_AUF_14B
@pytest.mark.slow
@pytest.mark.ollama
def test_peter_schreibt_kaufmaennisches_runden(client, tmp_path):
    """Die Falle ist Wissen, nicht Fleiß: `round()` rundet in Python zur
    geraden Zahl (2.5 → 2), und als float ist 2.675 in Wahrheit 2.67499….
    Bestehen kann nur, wer zu `decimal` mit ROUND_HALF_UP greift.

    Der Code des Modells läuft in einem eigenen Python-Prozess (`-I`,
    Zeitlimit, leeres tmp-Verzeichnis), nie im Testprozess.
    """
    antwort = _frage(client, _RUNDEN_AUFGABE)
    code = _code_aus_antwort(antwort)
    assert code, f"Keine Funktion runde_kaufmaennisch gefunden in:\n{antwort}"

    faelle = [[betrag, stellen] for betrag, stellen, _ in _RUNDEN_FAELLE]
    lauf = subprocess.run(
        [sys.executable, "-I", "-c", code + _HARNISCH, json.dumps(faelle)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )
    assert lauf.returncode == 0, f"Code bricht ab:\n{lauf.stderr}\n---\n{code}"
    zeilen = [z for z in lauf.stdout.splitlines() if z.strip()]
    ergebnisse = json.loads(zeilen[-1])

    falsch = [
        f"{betrag!r}, {stellen} → {ist!r} (erwartet {soll!r})"
        for (betrag, stellen, soll), ist in zip(_RUNDEN_FAELLE, ergebnisse)
        if ist != soll
    ]
    assert not falsch, "Falsch gerundet:\n" + "\n".join(falsch) + f"\n---\n{code}"


# ---- 2. Schlau sein: Geburtsort von damals, Staat von heute --------------------

_GEBURTSORT_FRAGE = (
    "In welchem heutigen Staat liegt jeweils der Geburtsort von 1) Immanuel Kant,"
    " 2) Arthur Schopenhauer, 3) Sigmund Freud? Antworte nur mit den drei"
    " heutigen Staaten in dieser Reihenfolge, durch Kommas getrennt."
)

# Kant: Königsberg → Kaliningrad. Schopenhauer: Danzig → Gdańsk.
# Freud: Freiberg in Mähren → Příbor. Die Köder sind Nationalität und
# Wirkungsort: „Deutschland", „Deutschland", „Österreich".
_GEBURTSORT_ERWARTET = ["russ", "polen", "tschech"]


@_WARTET_AUF_14B
@pytest.mark.slow
@pytest.mark.ollama
def test_peter_denkt_an_heutige_grenzen(client):
    """Zwei Schritte: erst den Geburtsort wissen, dann bedenken, dass sich die
    Grenzen seither verschoben haben. Wer bei Schopenhauer „Deutschland" oder
    bei Freud „Österreich" sagt, ist dem Köder gefolgt. Ohne Wiki — `client`
    schaltet es ab, das Wissen muss im Modell stecken.
    """
    antwort = _frage(client, _GEBURTSORT_FRAGE)
    norm = _normalize(antwort).rstrip(".")
    teile = [t.strip() for t in re.split(r",|;|\n| und ", norm) if t.strip()]

    assert (
        len(teile) == 3
    ), f"Erwartet drei Staaten, bekommen {teile!r} aus: {antwort!r}"
    falsch = [
        f"{nr}) {teil!r} (erwartet etwas mit {stamm!r})"
        for nr, (teil, stamm) in enumerate(zip(teile, _GEBURTSORT_ERWARTET), start=1)
        if stamm not in teil
    ]
    assert not falsch, "Falscher Staat:\n" + "\n".join(falsch) + f"\n---\n{antwort}"
