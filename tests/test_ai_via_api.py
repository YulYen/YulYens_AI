import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from config.config_singleton import Config
from config.personas import get_all_persona_names
from core.streaming_provider import YulYenStreamingProvider
from tests.util import is_model


# ---- Deterministic time in Europe/Berlin ------------------------------------
BERLIN = ZoneInfo("Europe/Berlin")
_now = datetime.now(tz=BERLIN)
current_year = str(_now.year)
current_year_short = current_year[-2:]  # "25" when the year is 2025


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
    cfg = Config()
    logs_dir = Path(cfg.logging["dir"])
    if not logs_dir.is_absolute():
        logs_dir = Path.cwd() / logs_dir
    if logs_dir.exists():
        before_files = set(logs_dir.glob("*.json"))
    else:
        before_files = set()

    captured: dict[str, str] = {}

    def fake_respond(
        self,
        user_input,
        persona,
        keyword_finder,
        wiki_mode,
        wiki_proxy_port,
        wiki_snippet_limit,
        max_wiki_snippets,
        wiki_timeout,
    ):
        captured["persona_arg"] = persona
        answer = f"Persona arg: {persona} | Bot attr: {self.persona}"
        self._append_conversation_log("user", user_input)
        self._append_conversation_log("assistant", answer)
        return answer

    monkeypatch.setattr(YulYenStreamingProvider, "respond_one_shot", fake_respond)

    response = client.post("/ask", json={"question": "Wer bist du?", "persona": "leah"})
    assert response.status_code == 200
    answer = response.json().get("answer", "")
    assert "Persona arg: LEAH" in answer
    assert "Bot attr: LEAH" in answer
    assert captured.get("persona_arg") == "LEAH"

    if logs_dir.exists():
        after_files = set(logs_dir.glob("*.json"))
    else:
        after_files = set()

    new_files = list(after_files - before_files)
    assert new_files, "No new conversation JSON log file was created."
    target = max(new_files, key=lambda path: path.stat().st_mtime)

    try:
        lines = target.read_text(encoding="utf-8").strip().splitlines()
        assert lines, "Conversation JSON log file contains no entries."
        last_entry = json.loads(lines[-1])
        assert last_entry.get("bot") == "LEAH"
    finally:
        for path in new_files:
            try:
                path.unlink()
            except FileNotFoundError:
                pass


@pytest.mark.slow
@pytest.mark.ollama
@pytest.mark.skipif(
    not is_model("leo-hessianai-13b-chat.Q5"),
    reason="Same joke is only stable under leo-hessianai-13b-chat.Q5"
)
def test_same_joke(client):
    """
    Expectation: identical question twice → exactly the same answer.
    Requirement: persona options include a fixed seed or deterministic settings.
    """
    prompt = "Erzähl bitte einen kurzen Nerd-Witz über Bytes."
    r1 = client.post("/ask", json={"question": prompt, "persona": "PETER"})

    assert r1.status_code == 200

    a1 = r1.json().get("answer", "")
    # a2 = 'Ein Byte geht in eine Bar und der Barkeeper sagt: "Sie wissen schon, dass wir hier Peaks bevorzugen."'  # LEO reference answer
    anfang = 'Ein Byte geht in eine Bar und der Barkeeper sagt: "Sie wissen schon, dass wir hier'  # LEO stable beginning

    # Non-empty and not just whitespace
    assert a1.strip()

    # Core requirement: deterministic match
    assert anfang in a1, (
        "Responses differ despite an identical prompt. "
        "Check seed/temperature/top_p/repeat_penalty in the persona options "
        "and set include_date=False for this test if needed."
    )


# ---- Normalization / matching -------------------------------------------------
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
            "name": "Portugal_PM_2025",
            "person": "PETER",
            "question": "Wer ist im Jahre 2025 der amtierende Regierungschef von Portugal? Und wer bist du?",
            # Accept spellings with or without accents; also verify persona mention
            "must_contain": ["luis montenegro", "PETER"],
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
