# CONTRIBUTING

## Voraussetzungen / Requirements
- Python 3.10 oder neuer (Python 3.10 or newer)

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

## Code Style
- Use **Black** and **Ruff** for formatting and linting (`make format` / `make lint`).
- Maximum line length: **88 characters**.
- **Wichtig:** Black/Ruff sind in `requirements-dev.txt` gepinnt (identisch zu
  `.pre-commit-config.yaml`). Eine abweichende lokale Black-Version formatiert
  anders und lässt die CI fehlschlagen.

## Tests
- Schneller lokaler Durchlauf (wie `make test`):
  ```bash
  pytest -q -m "not slow and not ollama"
  ```
- Vollständige Suite (Run the full test suite with):
  ```bash
  pytest -q
  ```
- Tests mit Marker `ollama` laufen nur, wenn lokal ein Ollama-Server erreichbar ist.

## PR Flow
- Submit small, focused pull requests.
- Reference the relevant issue in the PR description.
