# ADR-0003: Walking Skeleton Baseline (Naive Retrieval + Passthrough Rerank)

## Status
Accepted — 2026-06-09

## Context

The CLAUDE.md mandates eval-first discipline: every architectural change
requires a before/after eval delta. Before any retrieval optimization
(embedding model, reranking strategy, chunking), a reproducible baseline
must exist.

The TIPI Chapter 22 has only 34 distinct 8-digit NCMs. A trivial
classifier returning random candidates would expect top-1 accuracy near
1/34 ≈ 2.9%. A deterministic "first-k" classifier (no retrieval logic)
provides a slightly more honest floor: it captures whatever ordering
bias exists in the TIPI source data, without claiming intelligence.

## Decision

Implement a walking skeleton with two intentionally naive adapters:

- NaiveRetrievalAdapter: returns the first k entries from the TIPI JSON
  in source order, all with score=0.0
- PassthroughRerankAdapter: returns input candidates unchanged

This is composed end-to-end through ClassifyProduct use case and the
POST /classify HTTP endpoint, exercising the full hexagonal pipeline
without any LLM or embedding dependency.

## Baseline Measured (2026-06-09)

Eval set: eval/v1_cases.json (30 cases, Chapter 22 only)
TIPI version: Decreto 11.158/2022 (última atualização: Ato Declaratório Executivo RFB nº 1, de 30 de janeiro de 2026 (Retificado: DOU de 12/02/2026))

Overall:
  Top-1 accuracy:  1/30  = 3.3%
  Top-3 accuracy:  5/30  = 16.7%
  ECE:             not applicable (all scores = 0.0)

By difficulty:
  easy:    1/11 top-1,  4/11 top-3
  medium:  0/12 top-1,  1/12 top-3
  hard:    0/7  top-1,  0/7  top-3

Observations:

1. Top-1 (3.3%) slightly exceeds the random-classifier expectation
   (2.9%), confirming the "first-k" strategy captures minor ordering
   bias of the TIPI source rather than genuine signal.

2. Accuracy concentrates entirely in easy cases. Medium and hard cases
   are not solvable by source-ordering luck, as expected.

3. Top-3 (16.7%) is meaningfully above top-1 because the first 10
   entries returned by the naive adapter cover several common headings
   (2201, 2202, 2203, 2204) where easy cases tend to land.

4. ECE cannot be computed because all scores are 0.0 — the skeleton
   makes no probabilistic claims. ECE measurement becomes meaningful
   only after a real ranker assigns differentiated scores (ADR-0004).

## Consequences

Positive:
- Reproducible baseline: any developer can clone the repo and reproduce
  these exact numbers via `make eval` (depends only on versioned JSON,
  not on Chroma index or external API)
- RetrievalPort and LLMRerankPort validated against two distinct
  implementations (Naive and the upcoming Chroma; Passthrough and the
  upcoming Gemini), proving the abstraction works
- The full pipeline (HTTP → use case → adapters → TIPI data) is wired
  and observable end-to-end before any optimization
- All future architectural changes have a concrete delta to report
  against (Δtop-1, Δtop-3, ECE introduction)

Negative:
- The naive adapter is dead weight in production — it exists only as
  baseline anchor and must be retained at least until the ChromaDB-based
  adapter is fully validated
- No insight into which dimension matters most (embedding quality,
  chunking strategy, reranking) — baseline cannot disambiguate

Mitigations:
- Each future ADR introducing a retrieval improvement must isolate one
  variable at a time and report the eval delta from the immediate prior
  baseline (not from this one) — so improvements compound legibly
- NaiveRetrievalAdapter remains in src/retrieval/ as documented baseline
  artifact, marked WALKING SKELETON in its docstring

## Path Forward

The next architectural decision (ADR-0004) will introduce
ChromaRetrievalAdapter with semantic embeddings. Decisions pending in
that ADR:

- Embedding model selection (Gemini text-embedding-004 vs alternatives)
- Indexing granularity (per-NCM vs hierarchical with separate
  collections for sections/chapters/headings)
- k parameter for retrieval (currently 10, may change)
- Recalibration of confidence_threshold T (currently 0.7, untested
  against meaningful scores)

ADR-0004 must report:
- Top-1 and top-3 deltas vs this ADR's baseline
- First non-trivial ECE measurement
- Cost per classification (target ≤ R$ 0.10, stretch ≤ R$ 0.03 per
  CLAUDE.md)
- Median latency (target ≤ 4s, stretch ≤ 2s per CLAUDE.md)

## References

- CLAUDE.md (project guidance, eval-first discipline)
- eval/v1_cases.json (30 labeled cases)
- eval/run_eval.py (evaluate_suite + cross-validation)
- src/retrieval/naive_adapter.py (baseline implementation)
- src/llm/passthrough_adapter.py (baseline rerank)
- Commits 8078427 (pure factory refactor) + d5621a9 (eval integration; baseline captured)
