# tests/test_api_contract.py
import os
import re
import unicodedata
import requests
import pytest

API_URL = os.environ.get("LEAH_API_URL", "http://127.0.0.1:8013")

from datetime import datetime

current_year = str(datetime.now().year)
current_year_short = current_year[-2:]  # "25" bei 2025

def _normalize(s: str) -> str:
    """Kleines Normalisieren: Whitespace trimmen, Kleinbuchstaben,
    Umlaute/Akzente glätten (NFKD), Mehrfach-Leerzeichen reduzieren."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def ask(question: str) -> str:
    r = requests.post(f"{API_URL}/ask", json={"question": question}, timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("answer", "")

@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "Identitaet/Erfinder",
            "question": "Antworte bitte kurz: Wer bist du und wer hat dich erfunden?",
            "must_contain": ["PETER", "yul yen"],  # anpassbar
        },
        {
            "name": "Portugal_PM_2024",
            "question": "Antworte bitte kurz: Wer ist im Jahr 2025 Regierungschef von Portugal?",
            # akzeptiere Schreibweisen mit/ohne Akzent
            "must_contain": ["luis montenegro"],  # "luís" wird zu "luis" normalisiert
        },
        #Frage nach Jens Sphan ist deutlich schwerer, d.h. wir sparen hier Zeit
        #         {
        #    "name": "Bundeskanzler Merz",
        #   "question": "Antworte bitte kurz: Welches Amt bekleidet Friedrich Merz ab Mai 2025?",
        #  "must_contain": ["kanzler"],
        #},
                {
            "name": "Datum",
            "question": "Antworte bitte kurz: Welches Datum ist heute und welches Jahr haben wir?",
            "must_contain_any": [current_year, current_year_short],
        },
                        {
            "name": "Jens",
            "question": "Welches wichtige Amt bekleidet Jens Spahn aktuell?",
            "must_contain":[ "vorsitzender", "cdu", "fraktion"],
        },
    ],
)
def test_api_contract(case):
    ans_raw = ask(case["question"])
    ans = _normalize(ans_raw)

    missing = []
    if "must_contain" in case:
        for kw in case["must_contain"]:
            if _normalize(kw) not in ans:
                missing.append(kw)
    elif "must_contain_any" in case:
        if not any(_normalize(kw) in ans for kw in case["must_contain_any"]):
            missing = case["must_contain_any"]

    assert not missing, (
        f"Case '{case['name']}' fehlende Stichwörter: {missing}\n"
        f"Antwort war:\n{ans_raw}"
    )