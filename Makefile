.PHONY: run test eval eval-full eval-subheading lint fmt index snapshot

run:
	uvicorn src.main:app --reload --port 8000

test:
	pytest

eval:
	python -m eval.run_eval eval/v1_cases.json

# ADR-0005 experiment (FULL): heading + subheading + leaf. Net regression,
# kept reproducible. ENRICH_STRATEGY drives both the index strategy and the
# adapter's expected strategy, keeping index and eval in agreement. Default
# `eval` keeps the ADR-0004 baseline (strategy off).
eval-full:
	ENRICH_STRATEGY=full python -m src.retrieval.chroma_client rebuild
	ENRICH_STRATEGY=full python -m eval.run_eval eval/v1_cases.json

# ADR-0006 experiment (Form B): substantive 6-digit subheading + leaf; the
# 4-digit heading (broad family) is never injected.
eval-subheading:
	ENRICH_STRATEGY=subheading_only python -m src.retrieval.chroma_client rebuild
	ENRICH_STRATEGY=subheading_only python -m eval.run_eval eval/v1_cases.json

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
