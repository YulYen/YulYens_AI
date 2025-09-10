# tests/test_api_contract.py
import re
import unicodedata
import pytest


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

def ask(question: str, person: str, client) -> str:
    r1 = client.post("/ask", json={"question": question, "persona": person})
    return  r1.json().get("answer", "")

@pytest.mark.slow
@pytest.mark.ollama
@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "Identitaet/Erfinder",
            "person": "LEAH",
            "question": "Antworte bitte kurz: Wer bist du und wer hat dich erfunden?",
            "must_contain": ["LEAH", "yul yen"],  # anpassbar
        },
        {
            "name": "Portugal_PM_2024",
            "person": "PETER",
            "question": "Antworte bitte kurz: Wer ist im Jahr 2025 Regierungschef von Portugal? Und wer bist du?",
            # akzeptiere Schreibweisen mit/ohne Akzent
            "must_contain": ["luis montenegro", "PETER"],  # "luís" wird zu "luis" normalisiert
        },
                {
            "name": "Datum",
            "person": "PETER",
            "question": "Antworte bitte kurz: Welches Datum ist heute und welches Jahr haben wir?",
            "must_contain_any": [current_year, current_year_short],
        },
                        {
            "name": "Jens",
            "person": "PETER",
            "question": "Welches wichtige Amt bekleidet Jens Spahn aktuell?",
            "must_contain":[ "vorsitzend", "cdu", "fraktion"],
        },
    ],
)
def test_api_contract(case, client_with_date_and_wiki):
    ans_raw = ask(case["question"], case["person"], client_with_date_and_wiki)
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