# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

RAG pipeline that classifies Brazilian products into 8-digit NCM (Nomenclatura Comum do Mercosul) codes, grounded on the official TIPI table. Pure LLMs hallucinate NCM codes — this system retrieves before generating.

v1 scope: **Capítulo 22** (Bebidas, líquidos alcoólicos e vinagres), text input (product name + description ≤ 300 chars), top-3 candidates with confidence scores and TIPI citations.

## Tech Stack & Hard Constraints

- **Python 3.13**, FastAPI, ChromaDB (persistent), Pydantic
- **LLM**: Google Gemini — Flash for retrieval-side calls, Pro for verification
- **No LangChain, LlamaIndex, or LangGraph** — direct SDK calls only. Exception: if a library saves >200 lines, reconsider, but default is no.
- Deploy target: Fly.io or Railway (not localhost-only)

## Expected Structure

```
src/               # FastAPI application
data/tipi/         # TIPI source data (tipi_YYYYMMDD.json or .parquet)
eval/
  v1_cases.json    # 30 labeled products (ground truth)
  run_eval.py      # computes top-1, top-3, ECE metrics
  tipi_version.txt # TIPI version used when eval set was built
docs/adr/          # Architecture Decision Records (NNNN-title.md)
```

## Commands

```bash
make run        # start FastAPI dev server
make eval       # run eval/run_eval.py against the live classifier
make lint       # ruff + mypy
make test       # pytest
make index      # (re)build ChromaDB from data/tipi/*.json
make snapshot   # version embeddings for eval reproducibility
```

## Architecture

**RAG pipeline (hierarchical retrieval):**
1. Section → Chapter → Heading → NCM (structured, not flat vector search)
2. Confidence gate: above threshold T → return single classification; below T → escalate with ranked candidates
3. Verification step after retrieval: deterministic check against TIPI metadata — NCM exists in table, chapter coherent, digit-by-digit hierarchy consistent (see ADR-0002)

**Evaluation-first discipline:**
- `eval/v1_cases.json` must exist before the classifier is built
- Every architectural change (embedding model, chunking, re-ranking, prompt) requires a before/after eval delta committed in `docs/adr/`
- CI runs `eval/run_eval.py` on every push

**Success metrics (v1):**
| Metric | Target | Stretch |
|--------|--------|---------|
| Top-1 accuracy | ≥ 70% | ≥ 85% |
| Top-3 accuracy | ≥ 90% | ≥ 95% |
| Confidence calibration (ECE) | ≤ 0.15 | ≤ 0.08 |
| Median latency | ≤ 4s | ≤ 2s |
| Cost per classification | ≤ R$ 0.10 | ≤ R$ 0.03 |

## TIPI Reference Data

- **Source**: Decreto da TIPI vigente (versão consolidada — verificar versão atual antes de indexar)
- **File**: `data/tipi/tipi_YYYYMMDD.{json,parquet}`
- **Update policy**: re-indexar ChromaDB a cada revisão da TIPI; a versão usada no eval fica registrada em `eval/tipi_version.txt` para reproducibilidade

## Decision Log

All architectural decisions go in `docs/adr/NNNN-title.md`.

Resolved:
- **ADR-0001** — Capítulo 22 selecionado para v1 (ver `docs/adr/0001-chapter-selection.md`)
- **ADR-0002** — Verification via deterministic TIPI metadata check (ver `docs/adr/0002-verification-deterministic-check.md`)

Open:
- Confidence threshold T (set after first calibration run, not arbitrarily)
- Labeled eval data source (public NF-e SEFAZ samples vs. manual labeling)

## Out of Scope (v1)

Full TIPI coverage, image input, ERP/NF-e integration, batch processing, multi-tenant auth, composite products, IPI/ICMS rate lookup.
