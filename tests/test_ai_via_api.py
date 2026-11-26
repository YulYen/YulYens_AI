from yulyen_ai.config.personas import get_all_persona_names
from yulyen_ai.core.streaming_provider import YulYenStreamingProvider

# Die Live-Fälle (Identität, Portugal, Spahn, fünf Wörter) sind am 2026-11-26
# ins Lab umgezogen (`tests/test_live_api.py` dort): sie prüfen Modell und
# Prompt, nicht diese API.


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
    from yulyen_ai.core.factory import AppFactory
    from yulyen_ai.storage import SqliteStore

    store = SqliteStore(tmp_path / "conversations.sqlite3")
    monkeypatch.setattr(AppFactory, "get_store", lambda self: store)

    client.post("/ask", json={"question": "Wer bist du?", "persona": "leah"})

    refs = store.list_conversations()
    assert len(refs) == 1, "die API legt pro Anfrage genau ein Gespräch an"
    _ref, messages = store.load(refs[0].id)
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Wer bist du?"
    assert messages[1]["content"] == "ECHO: Wer bist du?"
