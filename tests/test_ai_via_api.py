import re
import unicodedata
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

# ---- Zeit deterministisch in Europe/Berlin -----------------------------------
BERLIN = ZoneInfo("Europe/Berlin")
_now = datetime.now(tz=BERLIN)
current_year = str(_now.year)
current_year_short = current_year[-2:]  # "25" bei 2025

def test_empty_question_rejected(client):
    response = client.post("/ask", json={"question": "", "persona": "PETER"})
    assert response.status_code == 200
    a1 =response.json().get("answer", "")
    a2 = "Bitte stell mir eine Frage 🙂"
    assert a1 == a2

@pytest.mark.slow
@pytest.mark.ollama
## TODO @pytest.mark.skipif(model =! "Leo13B", reason="Gleicher Witz Nur unter Leo stabil")
def test_same_joke(client):
    """
    Erwartung: zweimal gleiche Frage → exakt gleiche Antwort.
    Voraussetzung: Persona-Optionen enthalten einen fixen Seed bzw. deterministische Settings.
    """
    prompt = "Erzähl bitte einen kurzen Nerd-Witz über Bytes."
    r1 = client.post("/ask", json={"question": prompt, "persona": "PETER"})

    assert r1.status_code == 200

    a1 = r1.json().get("answer", "")
    a2 = 'Ein Byte geht in eine Bar und der Barkeeper sagt: "Sie wissen schon, dass wir hier Peaks bevorzugen."' #LEO

    # Nicht leer, keine reinen Whitespaces
    assert a1.strip() and a2.strip()

    # Kernforderung: deterministisch identisch
    assert a1 == a2, (
        "Antworten unterscheiden sich trotz identischem Prompt. "
        "Prüfe seed/temperature/top_p/repeat_penalty in den Persona-Optionen "
        "und setze ggf. include_date=False für diesen Test."
    )

# ---- Normalisierung / Matching ------------------------------------------------
def _normalize(s: str) -> str:
    """
    Kleines Normalisieren:
    - Trim
    - Kleinbuchstaben
    - Umlaute/Akzente glätten (NFKD)
    - Mehrfach-Leerzeichen reduzieren
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def _must_contain_all(ans_norm: str, items: list[str]) -> list[str]:
    missing = []
    for kw in items:
        if _normalize(kw) not in ans_norm:
            missing.append(kw)
    return missing

def _contains_any(ans_norm: str, items: list[str]) -> bool:
    return any(_normalize(kw) in ans_norm for kw in items)

# ---- API Helper ---------------------------------------------------------------
def ask(question: str, person: str, client) -> str:
    r = client.post("/ask", json={"question": question, "persona": person})
    # Defensiv: Falls Backend mal ein anderes Schema liefert
    try:
        data = r.json()
    except Exception:
        pytest.fail(f"Antwort ist kein JSON. Status={r.status_code}, Body={r.text[:500]}")

    # Typischer Vertrag: {"answer": "..."}; fallback: ganze JSON anzeigen
    return data.get("answer", str(data))

# ---- Testfälle ----------------------------------------------------------------
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
            "name": "Portugal_PM_2025",
            "person": "PETER",
            "question": "Wer ist im Jahr 2025 Regierungschef von Portugal? Und wer bist du?",
            # akzeptiere Schreibweisen mit/ohne Akzent; Persona-Hinweis mitprüfen
            "must_contain": ["luis montenegro", "PETER"],
        },
        {
            "name": "Jens_Spahn_Amt",
            "person": "PETER",
            "question": "Welches wichtige Amt bekleidet Jens Spahn aktuell? Und welches Datum haben wir heute?",
            # bewusst grob (schreibweise/Beugung tolerant)
            "must_contain": ["vorsitzend", "cdu", "fraktion"],
            "must_contain_any": [current_year, current_year_short],
        },
    ],
)
def test_api_contract(case, client_with_date_and_wiki):
    ans_raw = ask(case["question"], case["person"], client_with_date_and_wiki)
    ans = _normalize(ans_raw)

    missing_all = []
    if "must_contain" in case:
        missing_all = _must_contain_all(ans, case["must_contain"])

    ok_any = True
    if "must_contain_any" in case:
        ok_any = _contains_any(ans, case["must_contain_any"])

    ok = (not missing_all) and ok_any
    if not ok:
        # Präzise Diagnose
        fail_lines = [
            f"Case: {case.get('name')}",
            f"Persona: {case.get('person')}",
            f"Question: {case.get('question')}",
            f"Missing (must_contain): {missing_all}" if missing_all else "Missing (must_contain): []",
            f"Matched any (must_contain_any): {ok_any} (candidates={case.get('must_contain_any', [])})",
            "",
            "---- RAW ANSWER ----",
            ans_raw,
            "",
            "---- NORMALIZED ----",
            ans,
        ]
        pytest.fail("\n".join(fail_lines))