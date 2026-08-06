#!/bin/bash
# Startet eine Sitzung in der Sandbox arbeitsfähig (#74-Nachtrag).
#
# Zwei Dinge, die eine frische Sandbox sonst jede Sitzung neu kostet:
#
#   1. Sie kommt **leer** an. `pytest`, `ruff`, `mypy`, `lint-imports` — nichts
#      davon ist da, und das merkt man erst am `ModuleNotFoundError`.
#   2. Der Clone ist **flach**. `git tag` schweigt dann, und `git log --reverse`
#      behauptet, das Projekt sei ein paar Wochen alt. Genau darauf ist die
#      erste Runde von #74 hereingefallen: geplant war ein Tag `v1.0.0`, den es
#      seit November 2025 gibt.
#
# **Läuft ausschließlich remote.** Auf Yuls Rechner steht ein eingerichtetes
# venv, dort wäre ein `pip install` bei jedem Sitzungsstart Lärm und im
# schlimmsten Fall der falsche Interpreter; und flach ist der Clone dort auch
# nicht. Der Riegel ist `CLAUDE_CODE_REMOTE` — deshalb darf dieses Skript
# Linux annehmen und bash sein, obwohl das Projekt Windows-primär ist.
#
# Idempotent: was schon da ist, wird nicht noch einmal geholt. Und das Skript
# endet **immer** mit 0 — ein Werkzeug, das die Sitzung am Start scheitern
# lässt, ist schlimmer als die Handarbeit, die es ersetzt.

set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# --- 1. Historie vollständig machen -----------------------------------------
# Vor `git tag`, `git log --reverse` oder "gab es das schon mal?" muss der
# Clone tief sein. Ohne die Tags ist auch nicht zu sehen, welche Versionen
# bereits vergeben sind.
if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
  echo "[session-start] Clone ist flach — hole die volle Historie nach."
  git fetch --unshallow --tags origin || echo "[session-start] unshallow fehlgeschlagen (weiter ohne)."
else
  git fetch --tags origin >/dev/null 2>&1 || true
fi

# --- 2. Abhängigkeiten -------------------------------------------------------
# Die Probe fragt nach dem, was der Alltag zuerst braucht: die Testsuite und
# die Prüfwerkzeuge. Ist beides importierbar, ist nichts zu tun.
if python -c "import pytest, gradio, mypy" >/dev/null 2>&1; then
  echo "[session-start] Abhängigkeiten sind da."
else
  echo "[session-start] Installiere Laufzeit- und Entwicklungsabhängigkeiten…"
  python -m pip install -q -r requirements.txt -r requirements-dev.txt \
    || echo "[session-start] pip install fehlgeschlagen — 'make setup' von Hand nachholen."
fi

# Das spaCy-Modell (~575 MB) wird **nicht** geholt. Es schaltet nur die
# Keyword-/Wiki-Tests frei, die sonst sauber übersprungen werden — der
# Download bei jedem Sitzungsstart wäre der schlechtere Tausch.
# Wer sie braucht: python -m spacy download de_core_news_lg

exit 0
