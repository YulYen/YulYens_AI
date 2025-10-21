# CONTRIBUTING

## Voraussetzungen
- Python 3.10 oder neuer

## Setup
1. Virtuelle Umgebung erstellen:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Abhängigkeiten installieren:
   ```bash
   pip install -r requirements.txt
   ```

## Code-Style
- Formatierung und Linting mit **Black** und **Ruff**
- Maximale Zeilenlänge: **88 Zeichen**

## Tests
- Test-Suite ausführen mit:
  ```bash
  pytest -q
  ```

## PR-Flow
- Kleine, fokussierte Pull Requests einreichen
- Relevantes Issue im PR-Beschreibungstext referenzieren
