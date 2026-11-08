"""Live-Tests, die ein Modell der 14B-Klasse besteht und das 8B nicht (#78).

Seit 2026-11-07 ist `ministral-3:14b` der Default. Diese beiden Tests halten fest,
was es dem 8B voraus hat — kalibriert am 2026-11-08 auf Yuls Kiste, je 20 Läufe
mit PETERs Einstellungen aus dem Ensemble (siehe ``_KALIBRIERT``). Wer per
``config.local.yaml`` beim 8B bleibt, sieht sie also rot; das ist ihr Zweck.

Die Vorgänger (kaufmännisch runden, drei Geburtsorte nach heutigen Grenzen)
schaffte keines der beiden Modelle: 0 von 20 bei beiden. Sie maßen nur, dass
die Aufgaben zu schwer waren. Beim Runden lasen beide Modelle "2.675" außerdem
als deutschen Tausenderpunkt. Gesucht wurde deshalb in drei Runden nach
Aufgaben, die *trennen*; was beide schaffen (Wochentag, ISO-Kalenderwoche,
Palindrom mit Umlauten, Hauptstädte) oder beide nicht (IBAN-Prüfziffer,
Euro-Format), taugt dafür nicht. Messung und Kandidaten:
``docs/modellwechsel_november_2026.md``, Abschnitt „Messung auf Yuls Kiste".

Gegen ein anderes Modell, ohne die Config anzufassen (PowerShell)::

    $env:YULYEN_TEST_MODEL = "ministral-3:8b"
    python -m pytest tests/test_ai_via_api_14b.py -m ollama -rA
    Remove-Item Env:YULYEN_TEST_MODEL

`-rA` zeigt die Antwort des Modells auch bei bestandenen Tests.

Warum gerade diese Aufgaben: In Mistrals eigener Tabelle (Ministral-3-Paper,
arXiv 2601.08584) trennt einfacher Code die beiden Größen kaum (MBPP 70,0 gegen
71,6), Faktenwissen dagegen deutlich (TriviaQA 68,1 gegen 74,9). Beide Tests
brauchen deshalb Wissen: einmal einen Algorithmus, den man kennen muss, einmal
einen Ortsnamen.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import unicodedata

import pytest

# Kalibrierung 2026-11-08, je 20 Läufe, Ensemble "classic" wie ausgeliefert:
#   ostersonntag:  ministral-3:8b 0/20, ministral-3:14b 20/20
#   freud:         ministral-3:8b 0/20, ministral-3:14b 20/20  (mit Datum im Prompt;
#                  ohne Zeitstempel-Block schafft auch das 8B 20/20)
# Aufgenommen wird eine Aufgabe nur, wenn das 14B mindestens 19 von 20 schafft.
_KALIBRIERT = "2026-11-08"


def _frage(client, frage: str, persona: str = "PETER") -> str:
    response = client.post("/ask", json={"question": frage, "persona": persona})
    assert response.status_code == 200, response.text[:500]
    antwort = response.json().get("answer", "")
    # Für -rA: auch ein bestandener Lauf soll zeigen, wie die Antwort aussah.
    print(f"--- Antwort ---\n{antwort}")
    return antwort


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


# ---- 1. Coding: ein Algorithmus, den man kennen muss -----------------------------

_OSTERN_AUFGABE = (
    "Schreibe eine Python-Funktion ostersonntag(jahr: int) -> str, die das Datum"
    ' des (westlichen) Ostersonntags als "JJJJ-MM-TT" zurückgibt. Nur'
    " Standardbibliothek. Antworte nur mit dem Code in einem Python-Codeblock."
)

# Märzostern (2024, 1961), ein später Termin (2038) und die üblichen Jahre: wer
# Monat und Tag aus der Gaußschen Formel falsch zusammensetzt, verfehlt mindestens
# einen davon.
_OSTERN_FAELLE = [
    (2024, "2024-03-31"),
    (2025, "2025-04-20"),
    (2026, "2026-04-05"),
    (2019, "2019-04-21"),
    (2038, "2038-04-25"),
    (1961, "1961-04-02"),
]

_HARNISCH = """

import json as _json
import sys as _sys

print(_json.dumps([str(ostersonntag(j)) for j in _json.loads(_sys.argv[1])]))
"""


def _code_aus_antwort(antwort: str) -> str:
    bloecke = re.findall(r"```[a-zA-Z]*\s*\n(.*?)```", antwort, flags=re.DOTALL)
    for block in bloecke:
        if "def ostersonntag" in block:
            return block
    return antwort if "def ostersonntag" in antwort else ""


@pytest.mark.slow
@pytest.mark.ollama
def test_peter_berechnet_ostersonntag(client, tmp_path):
    """Das 8B kennt die Osterformel nur ungefähr und liefert Daten wie
    "2024-04--1"; das 14B schreibt sie richtig hin.

    Der Code des Modells läuft in einem eigenen Python-Prozess (`-I`,
    Zeitlimit, leeres tmp-Verzeichnis), nie im Testprozess.
    """
    antwort = _frage(client, _OSTERN_AUFGABE)
    code = _code_aus_antwort(antwort)
    assert code, f"Keine Funktion ostersonntag gefunden in:\n{antwort}"

    jahre = [jahr for jahr, _ in _OSTERN_FAELLE]
    lauf = subprocess.run(
        [sys.executable, "-I", "-c", code + _HARNISCH, json.dumps(jahre)],
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )
    assert lauf.returncode == 0, f"Code bricht ab:\n{lauf.stderr}\n---\n{code}"
    zeilen = [z for z in lauf.stdout.splitlines() if z.strip()]
    ergebnisse = json.loads(zeilen[-1])

    falsch = [
        f"{jahr} → {ist!r} (erwartet {soll!r})"
        for (jahr, soll), ist in zip(_OSTERN_FAELLE, ergebnisse)
        if ist != soll
    ]
    assert not falsch, "Falsches Osterdatum:\n" + "\n".join(falsch) + f"\n---\n{code}"


# ---- 2. Wissen: ein Geburtsort, der heute anders heißt --------------------------

_FREUD_FRAGE = (
    "Wie heißt der Geburtsort von Sigmund Freud heute, und in welchem Staat"
    " liegt er? Antworte in einem kurzen Satz."
)


@pytest.mark.slow
@pytest.mark.ollama
def test_peter_kennt_freuds_geburtsort(client_with_date):
    """Freiberg in Mähren heißt heute Příbor und liegt in Tschechien.

    Das 8B trifft den Staat, erfindet aber den Ort („Freiberg an der Jischl",
    „České Velenice"). Gefragt ist nur eine Person: Die Dreierfrage mit Kant und
    Schopenhauer davor lockte beide Modelle auf „Deutschland, Deutschland,
    Österreich".

    Mit Zeitstempel-Block (`client_with_date`), wie die App läuft: **Ohne** ihn
    weiß das 8B den Ort (20/20), mit ihm erfindet es ihn. Ohne Wiki: Das Wissen
    muss im Modell stecken.
    """
    antwort = _frage(client_with_date, _FREUD_FRAGE)
    norm = _normalize(antwort)
    assert "pribor" in norm, f"Erwartet Příbor als heutigen Ortsnamen:\n{antwort}"
    assert "tschech" in norm, f"Erwartet Tschechien als Staat:\n{antwort}"
