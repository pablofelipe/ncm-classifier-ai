.PHONY: run test eval lint fmt index snapshot

run:
	uvicorn src.main:app --reload --port 8000

test:
	pytest

eval:
	python -m eval.run_eval eval/v1_cases.json

lint:
	ruff check src eval
	ruff format --check src eval
	mypy src

fmt:
	ruff format src eval
	ruff check --fix src eval

index:
	python -m src.retrieval.chroma_client rebuild

snapshot:
	python -m src.retrieval.chroma_client snapshot
