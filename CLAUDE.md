# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

RAG pipeline that classifies Brazilian products into 8-digit NCM (Nomenclatura Comum do Mercosul) codes, grounded on the official TIPI table. Pure LLMs hallucinate NCM codes — this system retrieves before generating.

v1 scope: **Chapter 22** (Beverages, spirits and vinegar), text input (product name + description ≤ 300 chars), top-3 candidates with confidence scores and TIPI citations.

## Tech Stack & Hard Constraints

- **Python 3.13**, FastAPI, ChromaDB (persistent), Pydantic
- **LLM**: provider-agnostic rerank (ADR-0016) via `LLMClient`/`resolve_llm_client`; Google Gemini (`gemini-2.5-flash`) is the only implementation today, opt-in via `RERANK_MODE=gemini`. Verification is deterministic, not LLM-based (ADR-0002/0014)
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
make help       # list all targets with one-line descriptions
make run        # start FastAPI dev server
make eval       # run eval/run_eval.py against the live classifier (v1, CI baseline)
make lint       # ruff + format check + mypy
make test       # pytest (unit only)
make test-integration  # integration tests (downloads models, requires network)
make index      # (re)build ChromaDB from data/tipi/*.json
```

## Architecture

**RAG pipeline (hierarchical retrieval):**
1. Section → Chapter → Heading → NCM (structured, not flat vector search)
2. Confidence gate: above threshold T → return single classification; below T → escalate with ranked candidates
3. Verification step after rerank, before the confidence gate: deterministic check against TIPI metadata — NCM exists in the loaded index, digit-by-digit hierarchy consistent. Implemented in `src/core/verification/deterministic.py` and wired into `ClassifyProduct` via an optional `verification: TIPIIndex | None` constructor parameter, injected at the composition root (`src/api/dependencies.py`). A failing check forces `confidence_label="needs_review"` and sets `ClassificationResult.escalation_reason`, regardless of rerank score (see ADR-0002, wired in ADR-0014). Chapter-coherence, part of the original ADR-0002 design, was dropped at wiring time — see ADR-0014

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

Accepted — v2 measurement line (ships on the beverage corpus; v1/cap22 production untouched):
- **ADR-0009** — Dataset + corpus expansion: `eval/v2_cases.json` (350 cases) over a curated 64-NCM beverage corpus (`data/tipi/tipi_beverage_*.json`, Ch.20/21/22). Measured e5 OFF v2 baseline **20.3% top-1 / 32.6% top-3**; colloquial the dominant hole (20.5% top-3, 127/350). Recalibrated v2 targets to ≥40% / ≥65% (see `docs/adr/0009-dataset-corpus-expansion-v2-baseline.md`).
- **ADR-0010** — Corpus enrichment via synonyms file (`data/synonyms/beverage_synonyms.json`, 22 NCMs, 129 terms, evidence-bound to v2). Appended to OFF documents only in `build_document_text`; v1 blindado via `_synonyms_for_chapter` (synonyms gated to `NCM_CHAPTER=beverage`, cap22 stays 63.3%). v2 **20.3%→30.9% / 32.6%→51.7%** (+19.1 pp top-3); colloquial 20.5%→59.1%; `multi_attr` flat (Brix/volume aren't synonyms); −4 top-1 cases (all preserved in top-3). Below v2 targets; opens ADR-0011 (see `docs/adr/0010-corpus-enrichment-synonyms.md`).
- **ADR-0011** — Hybrid retrieval (BM25 + e5 via RRF, k=60). `BM25RetrievalAdapter` builds in memory from the stored Chroma documents (same synonym-enriched text, no JSON reread, no embedder prefix); `HybridRetrievalAdapter` fuses by `ncm_code`; `RetrievalMode` (env `RETRIEVAL_MODE`, default DENSE) wires it at the composition root. No index change — guard unchanged; RRF score is uncalibrated. v2 **30.9%→49.1% / 51.7%→68.0%** — **first config to clear both v2 targets** (≥40% / ≥65%). colloquial 59.1%→85.0% (synonyms + BM25 compound: synonyms inject the brand, BM25 makes the exact token decisive); no mode regressed. Opens ADR-0012 (see `docs/adr/0011-hybrid-retrieval-bm25-rrf.md`).

Rejected — domain gap, closes the local cross-encoder line:
- **ADR-0012** — Cross-encoder rerank with `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` REJECTED: hybrid+rerank **49.1%→20.3% / 68.0%→38.6%** (−28.8/−29.4 pp). Root: mMARCO cross-encoder trained on (question, web-passage) pairs; TIPI descriptions are 2-8 token fiscal nomenclature — domain gap produces near-random logits. Colloquial 85.0%→43.3% (the ADR-0010/0011 compounding gain destroyed). Infrastructure kept (`CrossEncoderRerankAdapter`, `RERANK_MODE`); production stays `PASSTHROUGH` (see `docs/adr/0012-cross-encoder-rerank-rejected.md`).

Accepted — LLM rerank, ships on v2 config:
- **ADR-0013** — Gemini 2.5 Flash LLM rerank (originally `GeminiRerankAdapter`, `RERANK_MODE=gemini`, top-5 pool, PT-BR fiscal prompt, `response_mime_type=application/json`). v2 **49.1%→71.7% / 68.0%→75.7%** (+22.6/+7.7 pp); negation +23.4 pp, frontier +21.7 pp; 0 JSON fallbacks; cost R$ 0.00013/query; latency ~2.1 s/query. Both v2 targets met with margin; top-1 exceeds v1 target on v2 corpus. `Makefile` target: `eval-gemini-rerank` (see `docs/adr/0013-gemini-flash-rerank.md`). **Superseded by ADR-0016**: `GeminiRerankAdapter` and `gemini_flash_model` were retired at that cutover, replaced by `GenericLLMRerankAdapter`/`resolve_llm_client`/`LLM_MODEL`, with confirmed accuracy parity.
- Confidence threshold T — `confidence_threshold=0.7` placeholder; calibration deferred (Gemini ranking order now drives top-3 selection, but scores are uncalibrated).

- **ADR-0014** — Verification gate wiring: `TIPIIndex.verify` wired into `ClassifyProduct` after rerank, via an optional constructor parameter injected at the composition root. Chapter-coherence check (part of ADR-0002's original design) dropped: a fixed `expected_chapter` doesn't fit the multi-chapter v2 corpus (`NCM_CHAPTER=beverage` spans Ch.20/21/22), and existence-in-index already covers the equivalent case for a corpus-scoped `TIPIIndex`. Kept: existence + hierarchy-consistency. A failing check forces `needs_review` + `escalation_reason`, without changing which candidates are returned (see `docs/adr/0014-verification-gate-wiring-chapter-coherence-dropped.md`).

- **ADR-0015** — Public deployment architecture (ships): the project is prepared for a public URL — deterministic Docker deploy, Chroma index baked into the image (no persistent volume), scale-to-zero, near-zero recurring cost. Central constraint: **the public server must hold no LLM credential of its own** — a shared `GEMINI_API_KEY` would let any visitor spend the maintainer's budget. This constraint is what motivated the provider-agnostic LLM integration (next ADR) rather than the other way around. Execution completed: live at [ncm-classifier-ai.fly.dev](https://ncm-classifier-ai.fly.dev), with API hardening (rate limiting, credential ergonomics) shipped alongside it (see `docs/adr/0015-public-deployment-architecture.md`, `docs/operational-notes.md` for real issues hit deploying).

- **ADR-0016** — Provider-agnostic LLM integration: `LLMRerankPort` unchanged; `GenericLLMRerankAdapter` (prompt/parsing logic) talks to an injected `LLMClient` (`generate(model, system_instruction, prompt, response_format)`), decoupling rerank from any vendor SDK. `GeminiClient` is the only `LLMClient` today; `resolve_llm_client(provider)` is a dict-keyed factory (`{"google": GeminiClient}`) — adding a provider is one entry, no change to `core/` or the composition root's branching. `Settings.llm_provider`/`llm_model` (plain `str`, not `StrEnum` — deliberately open) replace Gemini-specific config names. Per-request override: `X-LLM-Api-Key`/`LLM-Provider`/`LLM-Model` headers, read only in `src/api/dependencies.py::get_classify_use_case`, build an ephemeral adapter via `build_classify_use_case(rerank_override=...)` — the key lives only in that call's stack frame, never touches `settings` or a module global. This is the mechanism that implements ADR-0015's constraint: the public deployment can run with **no server-side LLM credential at all**. Cutover verified via a 30-case stratified parity check (identical top-1/top-3 before/after); full 350-case confirmation deferred by Gemini API instability during measurement. Accepted technical debt: `RerankMode.GEMINI` keeps its original name even though the mechanism is now fully generic — deferred rather than shipping a second breaking `RERANK_MODE` rename alongside `LLM_PROVIDER`/`LLM_MODEL` (see `docs/adr/0016-provider-agnostic-llm-integration.md`).

Path forward:
- Expand corpus and dataset beyond beverages (test generalization)
- Calibrate confidence scores (ECE currently uncalibrated; Gemini ranking order drives top-3 selection, but scores aren't probabilities)
- Rename `RerankMode.GEMINI` to something provider-neutral once a second `LLM_PROVIDER` is actually added (ADR-0016 technical debt)

Done (see ROADMAP.md/STATUS.md for the full picture): production Docker image (baked index, non-root, offline model cache), `GET /`, `/version`, `/info` diagnostics, `fly.toml`, public API hardening (rate limiting, clean provider-error responses, CORS, security headers, payload cap, provider timeout), and the live Fly.io deploy itself ([ncm-classifier-ai.fly.dev](https://ncm-classifier-ai.fly.dev)) — none of these are still open items.

Infra available (no re-implementation needed for experiments): configurable `EnrichStrategy` (enrichment line closed at 53.3%, kept reproducible) and configurable `EmbedderModel` + factory + dual index↔config guard (ADR-0008; bge opt-in via `EMBEDDER`, e5 OFF ships).

## Out of Scope (v1)

Full TIPI coverage, image input, ERP/NF-e integration, batch processing, multi-tenant auth, composite products, IPI/ICMS rate lookup.
