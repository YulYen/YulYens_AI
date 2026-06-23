# Framework-Update (Patch-Level) — Juni 2026

Konservatives **Patch-Level-Update** der Backend-Frameworks. Nur die dritte
Versionsstelle (X.Y.**Z**) wurde erhöht, Minor und Major bleiben fix — keine
Breaking Changes zu erwarten. Gradio/UI wurde **bewusst nicht angefasst**.

## Was sich geändert hat

| Paket | vorher | nachher | Art |
|---|---|---|---|
| `fastapi` | 0.111.0 | **0.111.1** | Patch (Bugfixes, gleiche Minor) |
| `uvicorn[standard]` | 0.30.1 | **0.30.6** | Patch (Bugfixes, gleiche Minor) |

Beide sind reines Backend (API/Server). Geändert wurde nur `requirements.txt`.

## Was bewusst NICHT geändert wurde

- **`gradio==4.44.1` / `gradio_client==1.3.0`** — absichtlich fixiert (Versionskonflikt-Schutz). `4.44.1` ist ohnehin die höchste Patch der 4.44er-Reihe; ein Sprung wäre Minor/Major und UI-riskant.
- **`pydantic==2.9.2`** — `>2.10` erzeugt ein bool-Schema und crasht `gradio_client` (siehe Kommentar in `requirements.txt`). `2.9.2` ist die höchste Patch der 2.9er-Reihe.
- **`starlette==0.37.2`, `annotated-types==0.7.0`** — bereits die höchste Patch ihrer Minor.
- **`black==24.4.2`, `ruff==0.4.10`** (dev) — höchste Patch ihrer Reihe; ein Minor-Sprung könnte Formatierung/Lint-Regeln ändern und die CI rot färben. Falls geändert: **immer synchron** in `requirements-dev.txt` **und** `.pre-commit-config.yaml` (siehe CLAUDE.md).
- Range-Pins (`requests`, `spacy`, `PyYAML`, `colorama`, `beautifulsoup4`, `ollama`, `pytest`, `pre-commit`) ziehen beim Install ohnehin die neueste kompatible Version — kein manueller Eingriff nötig.

## Lokal durchführen

```bash
# 1) Aktuellen Stand holen
git checkout main && git pull origin main

# 2) Virtualenv aktivieren (oder neu anlegen)
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 3) Abhängigkeiten aktualisieren (gepinnte Tool-Versionen inklusive)
pip install -r requirements.txt -r requirements-dev.txt

# 4) Schnelltests (ohne Ollama/langsame Tests)
pytest -q -m "not slow and not ollama"

# 5) Preflight-Check
python src/launch.py --doctor

# 6) Wenn Ollama läuft: vollständige Suite inkl. LLM-Tests
pytest -q

# 7) Formatierung/Lint wie in der CI
black --check . && ruff check .
pre-commit run --all-files     # falls pre-commit installiert
```

### Wichtig: Web-UI selbst antesten

Die FastAPI/Uvicorn-Bumps sind durch die Testsuite abgedeckt, **die Gradio-Web-UI
aber nicht** (Gradio wurde nicht verändert, lässt sich in CI/Headless schwer
prüfen). Einmal kurz manuell verifizieren:

```bash
python src/launch.py -e classic
```

Dann im Browser: eine Persona wählen, eine Nachricht senden (Streaming kommt an?),
"Neue Unterhaltung" klicken. Läuft das, ist das Update durch.

## Rollback (falls etwas klemmt)

```bash
git revert <commit-hash>     # den Update-Commit zurücknehmen
pip install -r requirements.txt -r requirements-dev.txt
```

Oder gezielt zurück auf die alten Versionen:

```bash
pip install "fastapi==0.111.0" "uvicorn[standard]==0.30.1"
```

## Verifikationsstand

Im Remote-Container vorab geprüft: `pip check` ohne Konflikte, Testsuite
**134 passed** (ohne Ollama/spaCy-Modelle), Black + Ruff sauber. Offen für dich:
der manuelle Web-UI-Smoke-Test (Schritt oben) und — falls Ollama läuft — `pytest -q`.
