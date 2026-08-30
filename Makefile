.PHONY: install run ui test lint qdrant-up qdrant-down rebuild evaluate

install:
	python -m pip install -r requirements-dev.txt

run:
	python -m uvicorn app.main:app --reload

ui:
	python -m streamlit run frontend/app.py

test:
	python -m pytest -q

lint:
	python -m ruff check app frontend tests

qdrant-up:
	docker compose up -d

qdrant-down:
	docker compose down

rebuild:
	python -m app.cli rebuild-index

evaluate:
	python -m app.cli evaluate
