# Tests für Yul Yen’s AI Orchestra
*English: Tests for Yul Yen’s AI Orchestra*

Diese README beschreibt die Test-Fixtures und wie du Test-Sets gezielt ausführst.
*English:* This README describes the test fixtures and how to run specific test sets.

**Wichtig:** Wir benutzen nur zwei Marker: `slow` und `ollama` – mehr nicht.
*Important:* We only use two markers: `slow` and `ollama`—nothing else.

---

## Fixtures
*English: Fixtures*

### `client`
- Baut einen **FastAPI TestClient** mit **echtem Provider** auf Basis deiner `AppFactory`.
- Lädt die **echte App** inkl. Konfiguration.
- **LLM-Nutzung:** Ja, sofern in deiner `config.yaml` ein reales Modell konfiguriert ist.
  (Wenn du ein Dummy-/Stubszenario willst, wähle explizit ein Dummy-Modell in der Config.)
- **Wiki/Datum:** In dieser Fixture wird `core.include_date` deaktiviert und der Wiki-Proxy **nicht** gestartet.

*English:*
- Builds a **FastAPI TestClient** with the **real provider** based on your `AppFactory`.
- Loads the **actual app** including configuration.
- **LLM usage:** Yes, provided that a real model is configured in your `config.yaml`.
  (If you want a dummy/stub scenario, explicitly select a dummy model in the config.)
- **Wiki/date:** In this fixture, `core.include_date` is disabled and the wiki proxy is **not** started.

**Typischer Einsatz:** Struktur-/Vertrags-Tests, die keine Wiki-Fakten benötigen.
*Typical usage:* Structural/contract tests that do not need wiki facts.

---

### `client_with_date_and_wiki`
- Wie `client`, aber zusätzlich:
  - Startet `start_wiki_proxy_thread()` und `ensure_kiwix_running_if_offlinemode_and_autostart(cfg)`.
  - Aktiviert Datum/Zeitausgaben gemäß Konfiguration.
- **LLM-Nutzung:** Ja (echtes Modell), plus **Wiki-Kontext** (offline/online je nach Config).

*English:*
- Like `client`, but additionally:
  - Starts `start_wiki_proxy_thread()` and `ensure_kiwix_running_if_offlinemode_and_autostart(cfg)`.
  - Enables date/time output according to configuration.
- **LLM usage:** Yes (real model), plus **wiki context** (offline/online depending on the config).

**Typischer Einsatz:** Tests, die LLM + Wiki zusammen prüfen (API → Provider → LLM → optional Wiki).
*Typical usage:* Tests that verify LLM + wiki together (API → provider → LLM → optional wiki).

---

## Marker
*English: Markers*

Wir halten es bewusst simpel:
*We intentionally keep it simple:*

- `@pytest.mark.slow`
  → Kennzeichnet Tests mit spürbarer Laufzeit (z. B. echte LLM-Antworten, Wiki-Aufrufe).
- `@pytest.mark.ollama`
  → Kennzeichnet Tests, die ein lauf- und erreichbares **Ollama-/LLM-Backend** voraussetzen.

*English:*
- `@pytest.mark.slow`
  → Labels tests with noticeable runtime (e.g., real LLM responses, wiki calls).
- `@pytest.mark.ollama`
  → Labels tests that require a running and reachable **Ollama/LLM backend**.

> **Kombination:** Ein Test, der realen LLM **und** Wiki nutzt, bekommt i. d. R. **beide** Marker: `@pytest.mark.slow` **und** `@pytest.mark.ollama`.
> *Combination:* A test that uses both a real LLM **and** wiki usually receives **both** markers: `@pytest.mark.slow` **and** `@pytest.mark.ollama`.

---

## Typische Aufrufe
*English: Typical invocations*

Nur Tests ohne LLM-Pflicht (z. B. reine String-/Utils-/Routing-Tests), **ausdrücklich** Marker aussparen:
*Only tests without LLM requirements (e.g., pure string/utils/routing tests) should **explicitly** skip markers:*

```bash
pytest -m "not ollama"
```

Nur „schwere“ LLM-Tests (mit echtem Modell), egal ob mit/ohne Wiki:
*Only “heavy” LLM tests (with a real model), regardless of wiki usage:*

```bash
pytest -m "ollama"
```

Nur markierte Langläufer **und** LLM:
*Only marked long-running tests **and** LLM:*

```bash
pytest -m "slow and ollama"
```

Alles laufen lassen:
*Run everything:*

```bash
pytest
```

---

## Hinweise zur Umgebung
*English: Environment notes*

### LLM/Backend (Ollama)
- Stelle sicher, dass dein Modell geladen/erreichbar ist (z. B. `ollama serve` und `ollama run <model>`).
- In `config.yaml` muss das **genaue Modell** und die Ollama-URL **explizit** gesetzt sein (keine stillen Defaults).

*English:*
- Make sure your model is loaded/reachable (e.g., `ollama serve` and `ollama run <model>`).
- In `config.yaml`, the **exact model** and the Ollama URL must be set **explicitly** (no silent defaults).

### Wiki-Proxy / Kiwix
- `client_with_date_and_wiki` startet den Wiki-Proxy über deine Projektfunktionen.
- **Offline-Modus:** Stelle sicher, dass **Kiwix** und die gewünschte **ZIM-Datei** verfügbar sind, falls `wiki.mode: offline` konfiguriert ist.
- Falls dein Proxy eine **Health-Route** hat, achte auf korrekte Konfig (Port/Mode).
  Startprobleme erkennst du in den Logs (`logs/wiki_proxy_*.log` bzw. deinem allgemeinen Log).

*English:*
- `client_with_date_and_wiki` starts the wiki proxy via your project functions.
- **Offline mode:** Ensure that **Kiwix** and the desired **ZIM file** are available if `wiki.mode: offline` is configured.
- If your proxy has a **health route**, verify the correct configuration (port/mode).
  You can spot startup issues in the logs (`logs/wiki_proxy_*.log` or your general log).

---

## Best Practices
*English: Best practices*

- **Deterministische Checks:** Verwende in Assertions Normalisierung (z. B. Kleinschreibung, Unicode-NFKD), um Akzente/Whitespace zu neutralisieren.
- **Zeitzone fixieren:** Für Datumstests Europe/Berlin nutzen (z. B. `zoneinfo.ZoneInfo("Europe/Berlin")`), um Mitternachts-Flakes zu vermeiden.
- **Explizite Config statt Magie:** Wenn ein Test ohne Wiki laufen soll, setze das **klar** in der Fixture/Config; wenn mit Wiki, nutze `client_with_date_and_wiki`.
- **Sinnvoll markieren:**
  - Funktioniert der Test **ohne** LLM? → **ohne** `ollama`.
  - Braucht er echtes Modell? → `@pytest.mark.ollama`.
  - Dauert er merklich länger? → zusätzlich `@pytest.mark.slow`.

*English:*
- **Deterministic checks:** Use normalization in assertions (e.g., lowercase, Unicode NFKD) to neutralize accents/whitespace.
- **Fix the time zone:** Use Europe/Berlin for date tests (e.g., `zoneinfo.ZoneInfo("Europe/Berlin")`) to avoid midnight flakiness.
- **Explicit config instead of magic:** If a test should run without the wiki, set that **clearly** in the fixture/config; if with wiki, use `client_with_date_and_wiki`.
- **Mark sensibly:**
  - Does the test work **without** an LLM? → **without** `ollama`.
  - Does it need a real model? → `@pytest.mark.ollama`.
  - Does it take noticeably longer? → add `@pytest.mark.slow` as well.

---

## Beispiel (Ausschnitt)
*English: Example (excerpt)*

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
*English: Troubleshooting*

- **Connection refused (Wiki/8042):**
  - Prüfe, ob `client_with_date_and_wiki` verwendet wird (der startet deinen Proxy).
  - Prüfe `wiki.mode` und Kiwix-Zugriff/ZIM-Datei.
  - Firewall-Freigaben (Windows Defender) beim ersten Start bestätigen.

  *English:*
  - Check whether `client_with_date_and_wiki` is used (it starts your proxy).
  - Check `wiki.mode` and Kiwix access/ZIM file.
  - Confirm firewall permissions (Windows Defender) on first launch.

- **LLM nicht erreichbar:**
  - `ollama serve` läuft?
  - `config.yaml` → `core.ollama_url` korrekt?
  - Modell lokal vorhanden (`ollama pull …`)?

  *English:*
  - Is `ollama serve` running?
  - Is `config.yaml` → `core.ollama_url` correct?
  - Is the model available locally (`ollama pull …`)?

- **Flaky Datumsantworten:**
  - Auf Zeitzone achten (`Europe/Berlin`).
  - In Assertions Jahr als `YYYY` **oder** `YY` akzeptieren (robust gegen Formatvarianten).

  *English:*
  - Pay attention to the time zone (`Europe/Berlin`).
  - Accept the year as `YYYY` **or** `YY` in assertions (robust against format variants).

---
