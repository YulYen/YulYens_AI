"""Live-Tests, die ein Modell der 14B-Klasse besteht und das 8B nicht (#78).

Seit 2026-11-07 ist `ministral-3:14b` der Default. Diese beiden Tests halten fest,
was es dem 8B voraus hat — kalibriert am 2026-11-08 auf Yuls Kiste, je 20 Läufe
mit PETERs Einstellungen aus dem Ensemble (siehe ``_KALIBRIERT``). Wer per
``config.local.yaml`` beim 8B bleibt, sieht sie also rot; das ist ihr Zweck.

Die Vorgänger (kaufmännisch runden, drei Geburtsorte nach heutigen Grenzen)
schaffte keines der beiden Modelle: 0 von 20 bei beiden. Zum Trennen von 8B und
14B taugen sie nicht; sie stehen geparkt am Ende dieses Moduls, als Messlatte
für ein schlaueres 16-GB-Modell (`YULYEN_ZUKUNFT_TESTS=1`). Beim Runden lasen beide Modelle "2.675" außerdem
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
import os
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


# ==== Geparkt für ein schlaueres Modell auf 16 GB ================================
#
# Die beiden ursprünglichen 14B-Tests. Am 2026-11-08 schafften sie weder
# ministral-3:8b noch ministral-3:14b (je 0/20; das Runden mit dem Klärungssatz
# zum Dezimalpunkt je 0/5). Sie bleiben als Messlatte für ein
# künftiges Modell, das noch auf 16 GB passt, und sind deshalb aus:
#
#     $env:YULYEN_ZUKUNFT_TESTS = "1"
#     $env:YULYEN_TEST_MODEL = "<neues Modell>"   # optional
#     python -m pytest tests/test_ai_via_api_14b.py -m ollama -rA
#
# Schafft ein Modell beide in mindestens 19 von 20 Läufen, wird es interessant —
# dann den Schalter entfernen oder ein neues Paar suchen, das trennt.

_FUER_SCHLAUERE_MODELLE = pytest.mark.skipif(
    os.environ.get("YULYEN_ZUKUNFT_TESTS") != "1",
    reason=(
        "Geparkt für ein schlaueres 16-GB-Modell: 8B und 14B je 0/20 "
        "(2026-11-08). Einschalten mit YULYEN_ZUKUNFT_TESTS=1."
    ),
)

_RUNDEN_AUFGABE = (
    "Schreibe eine Python-Funktion runde_kaufmaennisch(betrag: str, stellen: int)"
    " -> str. Sie bekommt einen Geldbetrag als Dezimal-String und rundet ihn"
    " kaufmännisch auf `stellen` Nachkommastellen: genau halbe Werte immer vom"
    " Nullpunkt weg. Rückgabe als String mit genau `stellen` Nachkommastellen."
    # Seit 2026-11-08: Ohne diesen Satz lasen 8B und 14B "2.675" als deutschen
    # Tausenderpunkt (2675) — dann misst der Test Leseverständnis, nicht Runden.
    ' Der Betrag nutzt den Punkt als Dezimaltrenner wie in Python: "2.675" heißt'
    " zwei Komma sechs sieben fünf, nicht zweitausendsechshundertfünfundsiebzig."
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

_RUNDEN_HARNISCH = """

import json as _json
import sys as _sys

_faelle = _json.loads(_sys.argv[1])
print(_json.dumps([str(runde_kaufmaennisch(b, s)) for b, s in _faelle]))
"""


def _runden_code_aus_antwort(antwort: str) -> str:
    bloecke = re.findall(r"```[a-zA-Z]*\s*\n(.*?)```", antwort, flags=re.DOTALL)
    for block in bloecke:
        if "def runde_kaufmaennisch" in block:
            return block
    return antwort if "def runde_kaufmaennisch" in antwort else ""


@_FUER_SCHLAUERE_MODELLE
@pytest.mark.slow
@pytest.mark.ollama
def test_peter_schreibt_kaufmaennisches_runden(client, tmp_path):
    """Die Falle ist Wissen, nicht Fleiß: `round()` rundet in Python zur
    geraden Zahl (2.5 → 2), und als float ist 2.675 in Wahrheit 2.67499….
    Bestehen kann nur, wer zu `decimal` mit ROUND_HALF_UP greift.
    """
    antwort = _frage(client, _RUNDEN_AUFGABE)
    code = _runden_code_aus_antwort(antwort)
    assert code, f"Keine Funktion runde_kaufmaennisch gefunden in:\n{antwort}"

    faelle = [[betrag, stellen] for betrag, stellen, _ in _RUNDEN_FAELLE]
    lauf = subprocess.run(
        [sys.executable, "-I", "-c", code + _RUNDEN_HARNISCH, json.dumps(faelle)],
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


_GEBURTSORT_FRAGE = (
    "In welchem heutigen Staat liegt jeweils der Geburtsort von 1) Immanuel Kant,"
    " 2) Arthur Schopenhauer, 3) Sigmund Freud? Antworte nur mit den drei"
    " heutigen Staaten in dieser Reihenfolge, durch Kommas getrennt."
)

# Kant: Königsberg → Kaliningrad. Schopenhauer: Danzig → Gdańsk.
# Freud: Freiberg in Mähren → Příbor. Die Köder sind Nationalität und
# Wirkungsort: „Deutschland", „Deutschland", „Österreich".
_GEBURTSORT_ERWARTET = ["russ", "polen", "tschech"]


@_FUER_SCHLAUERE_MODELLE
@pytest.mark.slow
@pytest.mark.ollama
def test_peter_denkt_an_heutige_grenzen(client):
    """Zwei Schritte: erst den Geburtsort wissen, dann bedenken, dass sich die
    Grenzen seither verschoben haben. Beide Modelle folgen dem Köder (je 0/20);
    das 14B antwortete alle 20 Mal „Deutschland, Deutschland, Österreich".
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
