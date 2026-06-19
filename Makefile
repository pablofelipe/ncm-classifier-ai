.PHONY: run test eval eval-v1 eval-v2 eval-full eval-subheading lint fmt index index-v2 snapshot

run:
	uvicorn src.main:app --reload --port 8000

test:
	pytest

# Default eval — v1 (30 cases, Ch.22). Unchanged so CI stays on the historical
# baseline (33.3% top-1 / 63.3% top-3). `eval-v1` is the explicit alias.
eval:
	python -m eval.run_eval eval/v1_cases.json

eval-v1:
	python -m eval.run_eval eval/v1_cases.json

# v2 (350 cases, multi-chapter). NCM_CHAPTER=beverage points retrieval at the
# expanded collection (tipi_capbeverage) and the v2 loader at the multi-chapter
# corpus (tipi_beverage_*.json). v2 is local-only for now; CI stays on v1
# (CI v2 is deferred to ADR-0009). Requires `make index-v2` first.
eval-v2:
	NCM_CHAPTER=beverage python -m eval.run_eval eval/v2_cases.json

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

# Build the expanded beverage corpus (64 NCMs, Ch.20/21/22) into its own
# collection (tipi_capbeverage), isolated from the production tipi_cap22 index.
# Regenerate the source file first with: python scripts/ingest_tipi.py beverage
index-v2:
	NCM_CHAPTER=beverage python -m src.retrieval.chroma_client rebuild

snapshot:
	python -m src.retrieval.chroma_client snapshot
