# ADR-0012 — Local Cross-Encoder Rerank (REJECTED — domain gap)

**Date:** 2026-06-28
**Status:** Rejected — domain gap; production remains ADR-0011 hybrid
**Deciders:** Pablo Felipe

---

## Context

ADR-0011 cleared both v2 targets with hybrid BM25+e5 RRF: **49.1% top-1 / 68.0% top-3**.
The residual holes: `frontier` 43.5% top-3, `multi_attr` 45.5% top-3 — cases where the
right candidate is in the pool but ranked below top-3.

The next lever on the cost-ordered roadmap was a **local cross-encoder reranker**: scores each
(query, passage) pair with a bi-directional attention model, zero recurring API cost, no budget risk.

### Candidate model

`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`
- Trained on mMARCO (multilingual MS MARCO, includes Portuguese)
- ~120 MB, `sentence_transformers.CrossEncoder` API (same library as the e5 embedder)
- Revision pinned: `1427fd652930e4ba29e8149678df786c240d8825` (captured 2026-06-28)

---

## Decision

`CrossEncoderRerankAdapter` implemented (`src/llm/cross_encoder_adapter.py`):
- Implements `LLMRerankPort.rerank(query, candidates) → list[ClassificationCandidate]`
- Encoder injectable for unit tests (no model download in CI)
- Scores each `(product_name + description, candidate.description)` pair; sorts descending
- Raw logit score propagated to `ClassificationCandidate.score`
- Wired via `RERANK_MODE=cross_encoder` (default: `PASSTHROUGH`)

10 unit tests, all green; lint and mypy clean.

---

## Measured Result

Single deterministic run, v2 (350 cases), `RETRIEVAL_MODE=hybrid RERANK_MODE=cross_encoder`
over the synonym-enriched `tipi_capbeverage` collection. Baseline: ADR-0011.

### Aggregate

| Config | Top-1 | Top-3 | Δ Top-1 | Δ Top-3 |
|---|---|---|---|---|
| ADR-0011 hybrid (baseline) | 49.1% (172/350) | 68.0% (238/350) | — | — |
| + cross-encoder rerank (this ADR) | **20.3% (71/350)** | **38.6% (135/350)** | **−28.8 pp** | **−29.4 pp** |

### Per-mode (selected)

| Mode | Cases | ADR-0011 Top-3 | This ADR Top-3 | Δ |
|---|---|---|---|---|
| colloquial | 147 | 85.0% | 43.3% | **−41.7 pp** |
| direct | 65 | ~61.5% | 61.5% | ~0 pp |

Colloquial — the mode that benefited most from ADR-0010 synonyms + ADR-0011 BM25 (20.5% → 85.0%) — is
the mode most destroyed: −41.7 pp, back to below the ADR-0010 dense baseline (59.1%).

---

## Root Cause — Domain Gap

mmarco-mMiniLMv2 was trained on MS MARCO pairs:
- **Query**: natural language question typed by a web user
- **Passage**: 100-400 token natural language prose document

TIPI NCM descriptions are structurally incompatible:
- **2-8 tokens** of fiscal nomenclature (e.g., `"Uísques de malte escocês"`, `"Cervejas de malte"`)
- Hierarchical noun phrases, not natural language
- Dense information density; no discourse structure the model can exploit

The model produces near-random logits for (colloquial product name, TIPI notation) pairs.
When the hybrid retriever places the correct answer at rank 1–3, the cross-encoder demotes it
to rank 4+ with high probability — a systematic inversion, not noise.

### Why colloquial is hit hardest

ADR-0011's key win: synonyms put the brand token in the TIPI document, BM25 makes the
exact-match decisive — "Chivas" → `2208.30.20`. A colloquial query has zero token overlap with
the TIPI description. The cross-encoder assigns near-zero relevance to the correct passage and
systematically promotes shorter or accidentally similar strings above it.

### Scope of failure — not model-specific

All cross-encoders in the MS MARCO family (ms-marco-MiniLM, mmarco-MiniLM, mmarco-mMiniLM) share
the same domain. A different MARCO model would face the same gap. A domain-appropriate
Portuguese fiscal cross-encoder does not exist in the HuggingFace Hub at this time.
Fine-tuning on `eval/v2_cases.json` (350 pairs) is insufficient for a cross-encoder.

---

## Consequences

**Infrastructure kept.** `CrossEncoderRerankAdapter`, `RerankMode`, and `RERANK_MODE`
remain in the codebase. `LLMRerankPort` is exercised by `PassthroughRerankAdapter` in
production. If a domain-appropriate model appears, it can be wired with zero structural changes.

**Production unchanged.** `RERANK_MODE` defaults to `PASSTHROUGH`; CI runs at default;
ADR-0011 hybrid (49.1% / 68.0%) remains the shipping config.

**Path forward — ADR-0013: LLM rerank.** An instruction-following LLM understands
the relationship between colloquial product names and fiscal nomenclature without fine-tuning.
It must be measured against the R$ 0.10 / 4 s budget. Recalibrating the v1 target is the fallback.

---

## Eval Invocation

```bash
# ADR-0011 baseline (unchanged)
make eval-v2

# This ADR — for reproducibility only; causes regression; do not use in production
make eval-rerank
```
