.PHONY: format lint fix test test-all clean run

format:
	black .

lint:
	ruff check .

fix:
	ruff check --fix .

test:
	pytest -q -m "not slow and not ollama"

test-all:
	pytest -q

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -name "*.pyc" -delete

run:
	python src/launch.py -e classic
