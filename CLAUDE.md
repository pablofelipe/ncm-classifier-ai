# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

RAG pipeline that classifies Brazilian products into 8-digit NCM (Nomenclatura Comum do Mercosul) codes, grounded on the official TIPI table. Pure LLMs hallucinate NCM codes — this system retrieves before generating.

v1 scope: **Chapter 22** (Beverages, spirits and vinegar), text input (product name + description ≤ 300 chars), top-3 candidates with confidence scores and TIPI citations.

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

- **Source**: current TIPI decree (consolidated version — check the current version before indexing)
- **File**: `data/tipi/tipi_<chapter>_YYYYMMDD.json` per chapter (v1: `tipi_22_*`). The v2 corpus is a single curated multi-chapter file `data/tipi/tipi_beverage_YYYYMMDD.json` (Ch.22 whole + Ch.20/2009 + Ch.21/2101+2106.90.10 = 64 NCMs), regenerable via `python scripts/ingest_tipi.py beverage`. Indexed into its own `tipi_capbeverage` collection (`NCM_CHAPTER=beverage`), isolated from production `tipi_cap22`.
- **Update policy**: re-index ChromaDB on every TIPI revision; the version used in eval is recorded in `eval/tipi_version.txt` for reproducibility

## Decision Log

All architectural decisions go in `docs/adr/NNNN-title.md`.

Resolved:
- **ADR-0001** — Chapter 22 selected for v1 (see `docs/adr/0001-chapter-selection.md`)
- **ADR-0002** — Verification via deterministic TIPI metadata check (see `docs/adr/0002-verification-deterministic-check.md`)
- **ADR-0003** — Walking-skeleton baseline (see `docs/adr/0003-walking-skeleton.md`)
- **ADR-0004** — Semantic retrieval with e5-small; baseline 33.3% top-1 / 63.3% top-3 (see `docs/adr/0004-semantic-retrieval-e5-small.md`)
- Labeled eval data source — built as `eval/v1_cases.json` (30 cases: 28 ecommerce listings + 2 labeled); the ground truth for every ADR since 0004. **Frozen** for retroactive comparison.
- **eval/v2_cases.json** (350 cases, ADR-0009) — multi-chapter (Ch.20/21/22), `mode`-tagged (colloquial/poverty/negation/frontier/multi_attr/direct). Separate `EvalCaseV2`/`EvalSuiteV2` schema; `run_eval` auto-detects v1 vs v2 by the `corpus_chapters` key. Local only; CI stays on v1.

Accepted with regression — flagged, not shipped (production stays on the `OFF` baseline, 63.3% top-3):
- **ADR-0005** — Full hierarchical enrichment (heading + subheading + leaf): top-3 63.3% → 53.3% (see `docs/adr/0005-hierarchical-enrichment.md`)
- **ADR-0006** — Subheading-only enrichment (Form B): best top-1 (43.3%) but top-3 ties FULL at 53.3%; homogenization is level-agnostic (see `docs/adr/0006-subheading-only-enrichment.md`)

Rejected — closes the enrichment line:
- **ADR-0007** — Selective enrichment (Form C) rejected without measuring: a binary structural discriminator exists but injects only 5/34 leaves with an OFF-tie ceiling; root finding consolidates 0005–0007 — the bottleneck is e5-small's discriminative power between siblings, not document context (see `docs/adr/0007-selective-enrichment-rejected.md`).

Rejected — closes the offline retrieval-quality line:
- **ADR-0008** — Embedder swap to bge-m3 rejected: bge OFF regressed −20 pp top-3 (43.3%), bge FULL recovered only to 53.3% (the enrichment ceiling), neither beats e5 OFF (63.3%). Offline manipulation (document text *or* embedder) is exhausted; remaining failures are query-understanding + ranking, not document representation. Infra kept (configurable embedder + dual guard, bge opt-in via `EMBEDDER`); e5-small OFF still ships (see `docs/adr/0008-embedder-swap-bge-m3-rejected.md`).

Path forward (cost-ordered, rerank LAST — corrected from the earlier "ADR-0009 = rerank"):
- **ADR-0009** — Dataset + corpus expansion (this line): `eval/v2_cases.json` (350 cases) over a curated 64-NCM beverage corpus (`data/tipi/tipi_beverage_*.json`, Ch.20/21/22). Widens the measurement surface and isolates query-understanding failures by `mode` before any accuracy work; prevents overfitting the 30-case v1 set. Infra landed; v2 measurement itself is the next step.
- **ADR-0010** — Corpus enrichment (commercial descriptions, synonyms, brand names) — offline, cheap; attacks the colloquial/brand gap on the document side.
- **ADR-0011** — Hybrid retrieval (BM25 + e5): lexical recall fused with dense; zero recurring cost.
- **ADR-0012** — Local cross-encoder rerank (BGE/Jina/MS-MARCO): the ranking-precision lever, zero recurring API cost.
- **ADR-0013** — LLM rerank (last resort): reorder e5 OFF's top-k with an LLM that understands colloquial input and negation. Must measure recurring cost + latency against the R$ 0.10 / 4 s budget, not only accuracy. Recalibrating the v1 target is the fallback.
- Confidence threshold T — still the `confidence_threshold=0.7` placeholder; calibration awaits a real rerank stage (rerank is Passthrough today).

Infra available (no re-implementation needed for experiments): configurable `EnrichStrategy` (enrichment line closed at 53.3%, kept reproducible) and configurable `EmbedderModel` + factory + dual index↔config guard (ADR-0008; bge opt-in via `EMBEDDER`, e5 OFF ships).

## Out of Scope (v1)

Full TIPI coverage, image input, ERP/NF-e integration, batch processing, multi-tenant auth, composite products, IPI/ICMS rate lookup.
