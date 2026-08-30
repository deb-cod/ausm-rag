.PHONY: install run test lint qdrant-up qdrant-down rebuild evaluate

install:
	python -m pip install -e ".[dev]"

run:
	python -m uvicorn app.main:app --reload

test:
	python -m pytest -q

lint:
	python -m ruff check app tests

qdrant-up:
	docker compose up -d

qdrant-down:
	docker compose down

rebuild:
	python -m app.cli rebuild-index

evaluate:
	python -m app.cli evaluate

