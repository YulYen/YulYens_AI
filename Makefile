.PHONY: setup format lint fix test test-ci test-all coverage clean run

setup:
	pip install -r requirements.txt -r requirements-dev.txt
	python -m spacy download de_core_news_lg
	pre-commit install

format:
	black .

lint:
	ruff check .

fix:
	ruff check --fix .

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
