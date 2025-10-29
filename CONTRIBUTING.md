# CONTRIBUTING

## Voraussetzungen / Requirements
- Python 3.10 oder neuer (Python 3.10 or newer)

## Setup
1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Code Style
- Use **Black** and **Ruff** for formatting and linting.
- Maximum line length: **88 characters**.

## Tests
- Test-Suite ausführen mit (Run the test suite with):
  ```bash
  pytest -q
  ```

## PR Flow
- Submit small, focused pull requests.
- Reference the relevant issue in the PR description.
