.PHONY: help run test test-integration eval eval-v1 eval-v2 eval-full eval-subheading lint fmt index index-v2

.DEFAULT_GOAL := help

help:  ## list available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' Makefile | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "%-20s %s\n", $$1, $$2}'

run:  ## start the FastAPI dev server (uvicorn, port 8000)
	uvicorn src.main:app --reload --port 8000

test:  ## run unit tests only (tests/unit)
	pytest

test-integration:  ## run integration tests (downloads models, requires network)
	pytest tests/integration -v

# Default eval — v1 (30 cases, Ch.22). Unchanged so CI stays on the historical
# baseline (33.3% top-1 / 63.3% top-3). `eval-v1` is the explicit alias.
eval:  ## run the v1 eval (30 cases, Ch.22) — the CI baseline
	python -m eval.run_eval eval/v1_cases.json

eval-v1:  ## run the v1 eval (explicit alias of `eval`)
	python -m eval.run_eval eval/v1_cases.json

# v2 (350 cases, multi-chapter). NCM_CHAPTER=beverage points retrieval at the
# expanded collection (tipi_capbeverage) and the v2 loader at the multi-chapter
# corpus (tipi_beverage_*.json). v2 is local-only for now; CI stays on v1.
# Requires `make index-v2` first.
eval-v2:  ## run the v2 eval (350 cases, Ch.20/21/22); needs `make index-v2`
	NCM_CHAPTER=beverage python -m eval.run_eval eval/v2_cases.json

# ADR-0005 experiment (FULL): heading + subheading + leaf. Net regression,
# kept reproducible. ENRICH_STRATEGY drives both the index strategy and the
# adapter's expected strategy, keeping index and eval in agreement.
eval-full:  ## ADR-0005 experiment: reindex + eval with FULL enrichment
	ENRICH_STRATEGY=full python -m src.retrieval.chroma_client rebuild
	ENRICH_STRATEGY=full python -m eval.run_eval eval/v1_cases.json

# ADR-0006 experiment (Form B): substantive 6-digit subheading + leaf; the
# 4-digit heading (broad family) is never injected.
eval-subheading:  ## ADR-0006 experiment: reindex + eval with SUBHEADING_ONLY
	ENRICH_STRATEGY=subheading_only python -m src.retrieval.chroma_client rebuild
	ENRICH_STRATEGY=subheading_only python -m eval.run_eval eval/v1_cases.json

lint:  ## ruff check + format check + mypy
	ruff check src eval
	ruff format --check src eval
	mypy src

fmt:  ## auto-format and auto-fix (ruff)
	ruff format src eval
	ruff check --fix src eval

index:  ## (re)build the ChromaDB index for the production chapter (Ch.22)
	python -m src.retrieval.chroma_client rebuild

# Build the expanded beverage corpus (64 NCMs, Ch.20/21/22) into its own
# collection (tipi_capbeverage), isolated from the production tipi_cap22 index.
# Regenerate the source file first with: python scripts/ingest_tipi.py beverage
index-v2:  ## build the isolated beverage index (64 NCMs, tipi_capbeverage)
	NCM_CHAPTER=beverage python -m src.retrieval.chroma_client rebuild
