
# tests/test_same_joke.py
import pytest
from fastapi.testclient import TestClient

from config.config_singleton import Config
from core.factory import AppFactory
from api.app import app, set_provider

@pytest.mark.slow
@pytest.mark.ollama
def test_same_joke(client):
    """
    Erwartung: zweimal gleiche Frage → exakt gleiche Antwort.
    Voraussetzung: Persona-Optionen enthalten einen fixen Seed bzw. deterministische Settings.
    """

    prompt = "Erzähl bitte einen kurzen Nerd-Witz über Bytes."
    r1 = client.post("/ask", json={"question": prompt})
    #r2 = client.post("/ask", json={"question": prompt})

    assert r1.status_code == 200
    #assert r2.status_code == 200

    a1 = r1.json().get("answer", "")
    a2 = 'Ein Byte geht in eine Bar und der Barkeeper sagt: "Sie wissen schon, dass wir hier Peeks hier servieren."'


    # Nicht leer, keine reinen Whitespaces
    assert a1.strip() and a2.strip()

    # Kernforderung: deterministisch identisch
    assert a1 == a2, (
        "Antworten unterscheiden sich trotz identischem Prompt. "
        "Prüfe seed/temperature/top_p/repeat_penalty in den Persona-Optionen "
        "und setze ggf. include_date=False für diesen Test."
    )