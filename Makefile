.PHONY: format lint fix

format:
black .

lint:
ruff check .

fix:
ruff check --fix .
