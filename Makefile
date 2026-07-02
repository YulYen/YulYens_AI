.PHONY: setup format lint fix test test-ci test-all coverage clean run

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

fix:
	python -m ruff check --fix .

test:
	pytest -q -m "not slow and not ollama"

# Same scope as CI (includes slow tests, plus coverage report)
test-ci:
	pytest -q -m "not ollama" --cov=src --cov-report=term-missing

test-all:
	pytest -q

coverage:
	pytest -q -m "not slow and not ollama" --cov=src --cov-report=term-missing

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -name "*.pyc" -delete

run:
	python src/launch.py -e classic
