import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from config.personas import get_all_persona_names
from core.streaming_provider import YulYenStreamingProvider

# ---- Deterministic time in Europe/Berlin ------------------------------------
BERLIN = ZoneInfo("Europe/Berlin")
_now = datetime.now(tz=BERLIN)
current_year = str(_now.year)
current_year_short = current_year[-2:]  # "25" when the year is 2025

_MONTHS_DE = [
    "januar",
    "februar",
    "märz",
    "april",
    "mai",
    "juni",
    "juli",
    "august",
    "september",
    "oktober",
    "november",
    "dezember",
]
_MONTHS_EN = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
current_month_de = _MONTHS_DE[_now.month - 1]
current_month_en = _MONTHS_EN[_now.month - 1]
today_iso = _now.strftime("%Y-%m-%d")


def test_empty_question_rejected(client):
    response = client.post("/ask", json={"question": "", "persona": "PETER"})
    assert response.status_code == 200
    a1 = response.json().get("answer", "")
    a2 = "Bitte stell mir eine Frage 🙂"
    assert a1 == a2


def test_invalid_persona_rejected(client):
    response = client.post("/ask", json={"question": "Hallo?", "persona": "UNKNOWN"})
    assert response.status_code == 400
    payload = response.json()
    detail = payload.get("detail", "")
    assert "Unknown persona" in detail
    assert "Available personas" in detail
    for name in get_all_persona_names():
        assert name in detail


def test_persona_name_normalized(client, monkeypatch):
    """Der Persona-Name wird normalisiert — 'leah' erreicht den Streamer als LEAH."""
    captured: dict[str, str] = {}

    def fake_respond(self, user_input, persona, wiki):
        captured["persona_arg"] = persona
        return f"Persona arg: {persona} | Bot attr: {self.persona}"

    monkeypatch.setattr(YulYenStreamingProvider, "respond_one_shot", fake_respond)

    response = client.post("/ask", json={"question": "Wer bist du?", "persona": "leah"})

    assert response.status_code == 200
    answer = response.json().get("answer", "")
    assert "Persona arg: LEAH" in answer
    assert "Bot attr: LEAH" in answer
    assert captured.get("persona_arg") == "LEAH"


def test_api_turns_are_recorded_in_the_store(client, monkeypatch, tmp_path):
    """Seit #54 ist der Store die Aufzeichnung, nicht mehr die Logdatei.

    Der Test ersetzte früher `respond_one_shot` komplett und rief die
    Aufzeichnung von Hand — er prüfte damit seine eigene Nachbildung, nicht den
    Weg, den eine echte Anfrage nimmt. Jetzt läuft der echte Pfad gegen das
    Dummy-Backend, und nur der Store wird untergeschoben.
    """
    from core.factory import AppFactory
    from storage import SqliteStore

    store = SqliteStore(tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(AppFactory, "get_store", lambda self: store)

    client.post("/ask", json={"question": "Wer bist du?", "persona": "leah"})

    refs = store.list_conversations()
    assert len(refs) == 1, "die API legt pro Anfrage genau ein Gespräch an"
    _ref, messages = store.load(refs[0].id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Wer bist du?"
    assert messages[1]["content"] == "ECHO: Wer bist du?"


def _normalize(s: str) -> str:
    """
    Light normalization:
    - Trim
    - Lowercase
    - Smooth umlauts/accents (NFKD)
    - Collapse repeated whitespace
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


def _extract_words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text, flags=re.UNICODE)


# ---- API Helper ---------------------------------------------------------------
def ask(question: str, person: str, client) -> str:
    r = client.post("/ask", json={"question": question, "persona": person})
    # Defensive: handle unexpected backend payloads
    try:
        data = r.json()
    except Exception:
        pytest.fail(
            f"Response is not JSON. Status={r.status_code}, Body={r.text[:500]}"
        )

    # Typical contract: {"answer": "..."}; fallback to showing the full JSON
    return data.get("answer", str(data))


# ---- Test cases ----------------------------------------------------------------
@pytest.mark.slow
@pytest.mark.ollama
@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "Identitaet/Erfinder_Datum",
            "person": "LEAH",
            "question": "Antworte bitte kurz: Wer bist du und wer hat dich erfunden? Und welches Datum haben wir heute?",
            "must_contain": ["LEAH", "yul"],  # adjustable
            "must_contain_any": [current_year, current_year_short],
        },
        {
            "name": "Portugal_PM_2025_TWO_WIKI_SNIPPETS",
            "person": "PETER",
            "question": "Wer bist du? Und wer sind im Mai 2025 Regierungschefs von Portugal und Deutschland?",
            # Accept spellings with or without accents; also verify persona mention
            "must_contain": ["luis montenegro", "PETER", "Friedrich Merz"],
        },
        {
            "name": "Jens_Spahn_Amt",
            "person": "PETER",
            "question": "Welches wichtige Amt bekleidet der Politiker Jens Spahn aktuell?",
            # Intentionally broad (tolerant to spelling and inflection)
            "must_contain": ["vorsitzend", "cdu", "fraktion"],
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
        # Provide precise diagnostics
        fail_lines = [
            f"Case: {case.get('name')}",
            f"Persona: {case.get('person')}",
            f"Question: {case.get('question')}",
            (
                f"Missing (must_contain): {missing_all}"
                if missing_all
                else "Missing (must_contain): []"
            ),
            f"Matched any (must_contain_any): {ok_any} (candidates={case.get('must_contain_any', [])})",
            "",
            "---- RAW ANSWER ----",
            ans_raw,
            "",
            "---- NORMALIZED ----",
            ans,
        ]
        pytest.fail("\n".join(fail_lines))


@pytest.mark.slow
@pytest.mark.ollama
def test_persona_reports_injected_today_date(client_with_date_and_wiki):
    """With include_date on, the real today's date is injected into the system
    prompt (Backlog #19). Asking for it should surface the *current* month and
    year — not a date from the model's training era. This is the behavioural
    counterpart to the deterministic prompt-assembly tests in
    tests/test_three_timestamps.py.
    """
    ans_raw = ask(
        "Welches Datum haben wir heute? Bitte nenne Tag, Monat und Jahr.",
        "LEAH",
        client_with_date_and_wiki,
    )
    ans = _normalize(ans_raw)

    assert current_year in ans, f"Current year {current_year} missing in: {ans_raw!r}"

    # Accept the localized month name, the ISO date, or the numeric month in an
    # ISO-style fragment (e.g. "-06-") so phrasing differences don't make it flaky.
    month_candidates = [
        current_month_de,
        current_month_en,
        today_iso,
        f"-{_now.month:02d}-",
    ]
    assert _contains_any(
        ans, month_candidates
    ), f"Current month not found (candidates={month_candidates}) in: {ans_raw!r}"


@pytest.mark.slow
@pytest.mark.ollama
def test_peter_antwortet_nur_sonne_oder_mond(client):
    ans_raw = ask("Antworte nur mit einem Wort: Sonne oder Mond?", "PETER", client)
    ans_norm = _normalize(ans_raw)
    words = _extract_words(ans_norm)

    assert (
        len(words) == 1
    ), f"Expected exactly one word, got {words!r} from: {ans_raw!r}"
    assert words[0] in {
        "sonne",
        "mond",
    }, f"Expected 'Sonne' or 'Mond', got {words[0]!r} from: {ans_raw!r}"


@pytest.mark.slow
@pytest.mark.ollama
def test_peter_antwortet_in_exakt_fuenf_woertern(client):
    ans_raw = ask(
        "Antworte mit genau fünf Wörtern. Was hilft gegen Langeweile?", "PETER", client
    )
    words = _extract_words(ans_raw)

    assert (
        len(words) == 5
    ), f"Expected exactly five words, got {len(words)} from: {ans_raw!r}"
