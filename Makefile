.PHONY: setup format lint lint-imports types fix test test-ci test-all test-browser coverage clean run audit check evals evals-full bench

# Editierbar: das Paket zeigt auf diesen Checkout (src/yulyen_ai/paths.py).
# Die Laufzeit-Pins kommen über pyproject.toml aus requirements.txt.
setup:
	python -m pip install -e . -r requirements-dev.txt
	python -m spacy download de_core_news_lg
	pre-commit install

# 'python -m' erzwingt die pip-installierten, gepinnten Versionen —
# nackte Binaries im PATH können neuere Versionen sein (siehe CLAUDE.md,
# "Bekannte Falle: PATH-Shadowing") und formatieren dann anders als die CI.
# Gilt genauso für pytest: ein `pytest` im PATH kann auf einen *anderen*
# Interpreter zeigen als `python` — dann fehlen plötzlich Pakete, die
# installiert sind. Genau so beim Bau von `make check` passiert.
format:
	python -m black .

# Black prüfend *und* Ruff — wie der lint-Job der CI. Fehlte Black hier, war
# `make check` grün und die CI rot (passiert 2026-11-26, PR #251).
lint:
	python -m black --check .
	python -m ruff check .

# Schichten als Vertrag (import-linter). Braucht das installierte Paket.
lint-imports:
	lint-imports

# Typprüfung über das ganze src (#52); Pfade stehen in pyproject.toml.
# Der zweite Lauf nimmt Windows an: mypy wertet `sys.platform` statisch aus,
# der winsound-Zweig ist auf Linux sonst ungeprüfter toter Code.
types:
	python -m mypy
	python -m mypy --platform win32

fix:
	python -m ruff check --fix .

test:
	python -m pytest -q -m "not slow and not ollama and not browser"

# Same scope as CI (includes slow tests, plus coverage report)
test-ci:
	python -m pytest -q -m "not ollama and not browser" --cov=yulyen_ai --cov-report=term-missing

test-all:
	python -m pytest -q -m "not browser"

# Rauchtest im echten Browser. Bewusst aus allen anderen Zielen ausgenommen:
# er braucht Playwright *und* einen Chromium-Build und dauert ~100 s.
#   pip install playwright && playwright install chromium
test-browser:
	python -m pytest -q -m browser

coverage:
	python -m pytest -q -m "not slow and not ollama and not browser" --cov=yulyen_ai --cov-report=term-missing

# Schwachstellen in den Abhängigkeiten gegen audit_allowlist.yaml halten (#61).
# Braucht Netz (OSV/PyPI). `pip install pip-audit` vorausgesetzt.
audit:
	python scripts/audit_deps.py

# Alles, was die CI auch prüft — ein Kommando vor dem Push.
# Reihenfolge nach Laufzeit: was in Sekunden fehlschlägt, schlägt zuerst fehl.
# Bewusst *ohne* `audit` (braucht Netz) und ohne `test-browser` (braucht einen
# Browser-Build); beide laufen getrennt.
check: lint lint-imports types test
	@echo "✓ Format, Schichten, Typen und Tests sind grün."

# Eval-Suite (#41). 'evals' braucht kein Modell, 'evals-full' braucht Ollama.
evals:
	python scripts/run_evals.py -e classic --guard-only

evals-full:
	python scripts/run_evals.py -e classic

# Stoppuhr (#42): Zeit bis zum ersten *ausgelieferten* Zeichen und Durchsatz.
# Braucht Ollama. `--backend dummy` prueft nur, dass der Harness laeuft.
bench:
	python scripts/run_bench.py -e classic

# Python statt find: das Projekt läuft Windows-primär, dort gibt es kein find.
clean:
	python -c "import pathlib, shutil; \
	[shutil.rmtree(p, ignore_errors=True) for d in ('__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache') \
	 for p in pathlib.Path('.').rglob(d)]; \
	[p.unlink(missing_ok=True) for p in pathlib.Path('.').rglob('*.pyc')]"

run:
	python -m yulyen_ai -e classic
