# Tests for Yul Yen’s AI Orchestra

This README explains the available pytest fixtures, markers, invocation patterns, environment requirements, and troubleshooting hints for the test suite.

---

## Fixtures

### `client`
- Builds a **FastAPI TestClient** using your `AppFactory` with the **real provider**.
- Loads the **actual application** including configuration.
- **LLM usage:** Enabled when a real model is configured in `config.yaml`. Select a dummy model in the configuration if you want a stubbed setup.
- **Wiki/date:** `core.include_date` is disabled and the wiki proxy is **not** started.
- **Typical usage:** Structural or contract tests that do not require wiki facts.

### `client_with_date_and_wiki`
- Extends the `client` fixture and additionally:
  - Starts `start_wiki_proxy_thread()` and `ensure_kiwix_running_if_offlinemode_and_autostart(cfg)`.
  - Enables date/time output according to the configuration.
- **LLM usage:** Yes (real model) plus **wiki context** (offline or online depending on the configuration).
- **Typical usage:** Tests that exercise the end-to-end path API → provider → LLM → optional wiki.

---

## Markers

We intentionally keep the marker set simple—only two markers are available:

- `@pytest.mark.slow`
  - Labels tests with noticeable runtime, such as real LLM responses or wiki calls.
- `@pytest.mark.ollama`
  - Labels tests that require a running and reachable **Ollama/LLM backend**.

> **Combination rule:** A test that uses both a real LLM **and** the wiki generally receives **both** markers: `@pytest.mark.slow` **and** `@pytest.mark.ollama`.

---

## Running selected tests

Use pytest’s `-m` flag to include or exclude the markers above:

```bash
pytest -m "not ollama"
```
Run only tests that do **not** require a real LLM (e.g., string, utility, or routing tests).

```bash
pytest -m "ollama"
```
Run only “heavy” LLM tests (real model required), regardless of whether they touch the wiki.

```bash
pytest -m "slow and ollama"
```
Run only tests marked as long-running **and** LLM-bound.

```bash
pytest
```
Run the entire test suite.

---

## Environment preparation

### LLM backend (Ollama)
- Ensure the model is loaded and reachable (e.g., start with `ollama serve` and `ollama run <model>`).
- Set the **exact model name** and the Ollama URL explicitly in `config.yaml`; the tests do not rely on hidden defaults.

### Wiki proxy / Kiwix
- `client_with_date_and_wiki` starts the wiki proxy through your project utilities.
- **Offline mode:** Provide Kiwix and the required ZIM file when `wiki.mode: offline` is configured.
- If the proxy exposes a health route, double-check the configuration (port and mode). Startup issues appear in `logs/wiki_proxy_*.log` or your general log output.

---

## Best practices

- **Deterministic assertions:** Normalise values in assertions (e.g., lowercase, Unicode NFKD) to neutralise accents and whitespace.
- **Fix the time zone:** Use `zoneinfo.ZoneInfo("Europe/Berlin")` for date tests to avoid midnight-related flakes.
- **Prefer explicit configuration:** When a test must run without the wiki, configure that explicitly in the fixture or test; when it needs the wiki, use `client_with_date_and_wiki`.
- **Mark responsibly:**
  - If the test succeeds without an LLM → leave off `ollama`.
  - If it needs a real model → add `@pytest.mark.ollama`.
  - If it takes noticeably longer → add `@pytest.mark.slow` as well.

---

## Example excerpt

```python
# tests/test_api_contract.py (illustrative example)

import pytest

@pytest.mark.slow
@pytest.mark.ollama
def test_portugal_prime_minister(client_with_date_and_wiki):
    r = client_with_date_and_wiki.post("/ask", json={
        "question": "Answer briefly: Who is Portugal's head of government in 2025?",
        "persona": "PETER"
    })
    data = r.json()
    txt = data.get("answer", "").lower()
    assert "montenegro" in txt
```

---

## Troubleshooting

- **Connection refused (Wiki/8042):**
  - Verify that the test uses `client_with_date_and_wiki` (it starts the proxy).
  - Check `wiki.mode`, Kiwix access, and availability of the required ZIM file.
  - Confirm firewall prompts (e.g., Windows Defender) during the first launch.

- **LLM unreachable:**
  - Ensure `ollama serve` is running.
  - Confirm that `config.yaml` → `core.ollama_url` is correct.
  - Pull the required model locally (`ollama pull …`).

- **Flaky date answers:**
  - Ensure the `Europe/Berlin` time zone is applied.
  - Allow date assertions to accept both `YYYY` and `YY` formats to tolerate format variations.
