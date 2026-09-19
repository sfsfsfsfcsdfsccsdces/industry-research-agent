.PHONY: install run test lint demo docker

install:
	python -m pip install -e ".[dev]"

run:
	python -m uvicorn app.main:app --reload

test:
	pytest -q

lint:
	ruff check .

demo:
	python scripts/run_demo.py

docker:
	docker compose up --build
