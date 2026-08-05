# CONTRIBUTING

## Voraussetzungen / Requirements
- Python 3.10 oder neuer (Python 3.10 or newer). Die CI prüft die **Enden**:
  3.10 auf Linux und Windows, 3.13 auf Linux. 3.11 und 3.12 sind gegen die
  volle Suite gefahren worden, laufen aber nicht bei jedem Push mit — jede
  Matrix-Zeile kostet CI-Minuten.

## Setup
1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies (runtime **and** pinned dev tools):
   ```bash
   pip install -r requirements.txt -r requirements-dev.txt
   ```
3. Install the spaCy German model (used by the wiki keyword finder and its tests;
   without it those tests are skipped):
   ```bash
   python -m spacy download de_core_news_lg
   ```
4. Enable the pre-commit hook (formats every commit with the CI-pinned
   Black/Ruff versions — see CLAUDE.md "Pre-commit / Versions-Pinning"):
   ```bash
   pre-commit install
   ```

Alternativ / shortcut: `make setup` führt die Schritte 2–4 aus.

## Vor dem Push: ein Kommando

```bash
make check
```

Fährt `make lint`, `make lint-imports`, `make types` und `make test` in dieser
Reihenfolge — was in Sekunden fehlschlägt, schlägt zuerst fehl. Bewusst **ohne**
`make audit` (braucht Netz) und ohne `make test-browser` (braucht einen
Browser-Build); beide laufen getrennt.

## Code Style
- Use **Black** and **Ruff** for formatting and linting (`make format` / `make lint`).
- **Schichten:** `make lint-imports` hält die Import-Struktur gegen die Verträge
  in `pyproject.toml` (`[tool.importlinter]`). Beispiel: der Guard darf nichts
  ausser der Config importieren, und nichts Unteres darf die Oberflächen kennen —
  bis auf drei namentlich eingetragene Ausnahmen in der AppFactory. Ein Verstoss
  nennt den konkreten Import-Pfad.
- Typprüfung mit mypy: `make types` (blockierend über das ganze `src`;
  Konfiguration in `pyproject.toml`). Das Ziel fährt **zwei** Läufe — den
  zweiten mit `--platform win32`, weil mypy `sys.platform` statisch auswertet
  und der Windows-Zweig auf Linux sonst ungeprüft bliebe.
- Maximum line length: **88 characters**.
- **Wichtig:** Black/Ruff sind in `requirements-dev.txt` gepinnt (identisch zu
  `.pre-commit-config.yaml`). Eine abweichende lokale Black-Version formatiert
  anders und lässt die CI fehlschlagen.

## Tests
- Schneller lokaler Durchlauf (wie `make test`):
  ```bash
  pytest -q -m "not slow and not ollama and not browser"
  ```
- Vollständige Suite (Run the full test suite with):
  ```bash
  pytest -q -m "not browser"
  ```
- Tests mit Marker `ollama` laufen nur, wenn lokal ein Ollama-Server erreichbar ist.
- Umfang wie in der CI, mit Coverage: `make test-ci`.
- Eval-Suite: `make evals` (Guard-Teil, braucht kein Modell) bzw. `make evals-full`
  (voll, braucht Ollama) — Details in `evals/ReadMe.md`.
- Marker `browser` fährt die laufende WebUI im echten Chromium (`make test-browser`).
  Er ist aus allen anderen Zielen und aus der CI ausgenommen, weil er Playwright
  **und** einen Browser-Build braucht; ohne Playwright wird sauber übersprungen.

## PR Flow
- Submit small, focused pull requests.
- Reference the relevant issue in the PR description.
