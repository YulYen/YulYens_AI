.PHONY: setup format lint types fix test test-ci test-all test-browser coverage clean run evals evals-full

setup:
	pip install -r requirements.txt -r requirements-dev.txt
	python -m spacy download de_core_news_lg
	pre-commit install

# 'python -m' erzwingt die pip-installierten, gepinnten Versionen —
# nackte Binaries im PATH können neuere Versionen sein (siehe CLAUDE.md,
# "Bekannte Falle: PATH-Shadowing") und formatieren dann anders als die CI.
format:
	python -m black .

lint:
	python -m ruff check .

# Typprüfung nur für src/core (#52); Pfade stehen in pyproject.toml.
types:
	python -m mypy

fix:
	python -m ruff check --fix .

test:
	pytest -q -m "not slow and not ollama and not browser"

# Same scope as CI (includes slow tests, plus coverage report)
test-ci:
	pytest -q -m "not ollama and not browser" --cov=src --cov-report=term-missing

test-all:
	pytest -q -m "not browser"

# Rauchtest im echten Browser. Bewusst aus allen anderen Zielen ausgenommen:
# er braucht Playwright *und* einen Chromium-Build und dauert ~100 s.
#   pip install playwright && playwright install chromium
test-browser:
	pytest -q -m browser

coverage:
	pytest -q -m "not slow and not ollama and not browser" --cov=src --cov-report=term-missing

# Eval-Suite (#41). 'evals' braucht kein Modell, 'evals-full' braucht Ollama.
evals:
	python scripts/run_evals.py -e classic --guard-only

evals-full:
	python scripts/run_evals.py -e classic

# Python statt find: das Projekt läuft Windows-primär, dort gibt es kein find.
clean:
	python -c "import pathlib, shutil; \
	[shutil.rmtree(p, ignore_errors=True) for d in ('__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache') \
	 for p in pathlib.Path('.').rglob(d)]; \
	[p.unlink(missing_ok=True) for p in pathlib.Path('.').rglob('*.pyc')]"

run:
	python src/launch.py -e classic
