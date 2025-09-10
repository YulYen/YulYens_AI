# Tests für Yul Yen’s AI Orchestra

Diese README beschreibt die Test-Fixtures und wie du Test-Sets gezielt ausführst.  
**Wichtig:** Wir benutzen nur zwei Marker: `slow` und `ollama` – mehr nicht.

---

## Fixtures

### `client`
- Baut einen **FastAPI TestClient** mit **echtem Provider** auf Basis deiner `AppFactory`.
- Lädt die **echte App** inkl. Konfiguration.
- **LLM-Nutzung:** Ja, sofern in deiner `config.yaml` ein reales Modell konfiguriert ist.  
  (Wenn du ein Dummy-/Stubszenario willst, wähle explizit ein Dummy-Modell in der Config.)
- **Wiki/Datum:** In dieser Fixture wird `core.include_date` deaktiviert und der Wiki-Proxy **nicht** gestartet.

**Typischer Einsatz:** Struktur-/Vertrags-Tests, die keine Wiki-Fakten benötigen.

---

### `client_with_date_and_wiki`
- Wie `client`, aber zusätzlich:
  - Startet `start_wiki_proxy_thread()` und `ensure_kiwix_running_if_offlinemode_and_autostart(cfg)`.
  - Aktiviert Datum/Zeitausgaben gemäß Konfiguration.
- **LLM-Nutzung:** Ja (echtes Modell), plus **Wiki-Kontext** (offline/online je nach Config).

**Typischer Einsatz:** Tests, die LLM + Wiki zusammen prüfen (API → Provider → LLM → optional Wiki).

---

## Marker

Wir halten es bewusst simpel:

- `@pytest.mark.slow`  
  → Kennzeichnet Tests mit spürbarer Laufzeit (z. B. echte LLM-Antworten, Wiki-Aufrufe).

- `@pytest.mark.ollama`  
  → Kennzeichnet Tests, die ein lauf- und erreichbares **Ollama-/LLM-Backend** voraussetzen.

> **Kombination:** Ein Test, der realen LLM **und** Wiki nutzt, bekommt i. d. R. **beide** Marker: `@pytest.mark.slow` **und** `@pytest.mark.ollama`.

---

## Typische Aufrufe

Nur Tests ohne LLM-Pflicht (z. B. reine String-/Utils-/Routing-Tests), **ausdrücklich** Marker aussparen:

```bash
pytest -m "not ollama"
```

Nur „schwere“ LLM-Tests (mit echtem Modell), egal ob mit/ohne Wiki:

```bash
pytest -m "ollama"
```

Nur markierte Langläufer **und** LLM:

```bash
pytest -m "slow and ollama"
```

Alles laufen lassen:

```bash
pytest
```


---

## Hinweise zur Umgebung

### LLM/Backend (Ollama)
- Stelle sicher, dass dein Modell geladen/erreichbar ist (z. B. `ollama serve` und `ollama run <model>`).
- In `config.yaml` muss das **genaue Modell** und die Ollama-URL **explizit** gesetzt sein (keine stillen Defaults).

### Wiki-Proxy / Kiwix
- `client_with_date_and_wiki` startet den Wiki-Proxy über deine Projektfunktionen.
- **Offline-Modus:** Stelle sicher, dass **Kiwix** und die gewünschte **ZIM-Datei** verfügbar sind, falls `wiki.mode: offline` konfiguriert ist.
- Falls dein Proxy eine **Health-Route** hat, achte auf korrekte Konfig (Port/Mode).  
  Startprobleme erkennst du in den Logs (`logs/wiki_proxy_*.log` bzw. deinem allgemeinen Log).

---

## Best Practices

- **Deterministische Checks:** Verwende in Assertions Normalisierung (z. B. Kleinschreibung, Unicode-NFKD), um Akzente/Whitespace zu neutralisieren.
- **Zeitzone fixieren:** Für Datumstests Europe/Berlin nutzen (z. B. `zoneinfo.ZoneInfo("Europe/Berlin")`), um Mitternachts-Flakes zu vermeiden.
- **Explizite Config statt Magie:** Wenn ein Test ohne Wiki laufen soll, setze das **klar** in der Fixture/Config; wenn mit Wiki, nutze `client_with_date_and_wiki`.
- **Sinnvoll markieren:**  
  - Funktioniert der Test **ohne** LLM? → **ohne** `ollama`.  
  - Braucht er echtes Modell? → `@pytest.mark.ollama`.  
  - Dauert er merklich länger? → zusätzlich `@pytest.mark.slow`.

---

## Beispiel (Ausschnitt)

```python
# tests/test_api_contract.py (Beispielidee)

import pytest

@pytest.mark.slow
@pytest.mark.ollama
def test_portugal_regierungschef(client_with_date_and_wiki):
    r = client_with_date_and_wiki.post("/ask", json={
        "question": "Antworte kurz: Wer ist 2025 Regierungschef von Portugal?",
        "persona": "PETER"
    })
    data = r.json()
    txt = data.get("answer", "").lower()
    assert "montenegro" in txt
```

---

## Troubleshooting

- **Connection refused (Wiki/8042):**  
  - Prüfe, ob `client_with_date_and_wiki` verwendet wird (der startet deinen Proxy).
  - Prüfe `wiki.mode` und Kiwix-Zugriff/ZIM-Datei.
  - Firewall-Freigaben (Windows Defender) beim ersten Start bestätigen.

- **LLM nicht erreichbar:**  
  - `ollama serve` läuft?  
  - `config.yaml` → `core.ollama_url` korrekt?  
  - Modell lokal vorhanden (`ollama pull …`)?

- **Flaky Datumsantworten:**  
  - Auf Zeitzone achten (`Europe/Berlin`).
  - In Assertions Jahr als `YYYY` **oder** `YY` akzeptieren (robust gegen Formatvarianten).

---
