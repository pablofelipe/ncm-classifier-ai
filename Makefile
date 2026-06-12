.PHONY: run test eval eval-enriched lint fmt index snapshot

run:
	uvicorn src.main:app --reload --port 8000

test:
	pytest

eval:
	python -m eval.run_eval eval/v1_cases.json

# ADR-0005 experiment: rebuild with hierarchical enrichment and eval against it.
# ENRICH_DOCUMENTS=1 drives both the index strategy and the adapter's expected
# flag, keeping index and eval in agreement (see ADR-0005). Default `eval` keeps
# the ADR-0004 baseline (enrich off).
eval-enriched:
	ENRICH_DOCUMENTS=1 python -m src.retrieval.chroma_client rebuild
	ENRICH_DOCUMENTS=1 python -m eval.run_eval eval/v1_cases.json

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
