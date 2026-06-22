# ADR-0011: Hybrid retrieval (BM25 + e5) via RRF

**Status:** Accepted (ships on the v2 beverage corpus, opt-in `RETRIEVAL_MODE=hybrid`) — first config to **clear both v2 targets**. Opens ADR-0012 (local cross-encoder rerank).

## Context

ADR-0010 lifted the v2 baseline to **30.9% top-1 / 51.7% top-3** by adding brands
and colloquial names to the document text, but left two holes the synonyms file
could not touch:

- **`multi_attr` flat at 39.4% top-3** — these cases turn on exact attribute
  tokens (`Brix 60`, `concentrado`, `anidro`, container volume) that are not
  synonyms; dense retrieval blurs them.
- **Hard-brand colloquial residual** — even with the brand in the document, the
  dense retriever only fuzzy-matches it; a rare proper-noun token (`Johnnie
  Walker`, `Chivas`) deserves an exact lexical hit, not a nearest-neighbour guess.

ADRs 0005–0008 closed offline document/embedder manipulation; ADR-0010 added
vocabulary. The remaining lever is **ranking** — fuse a lexical signal with the
dense one so exact-token matches resurface. BM25 is the cheapest such signal:
pure Python, zero recurring cost, no API.

## Decision

Hybrid retrieval, selectable at the composition root, fusing two `RetrievalPort`
implementations with **Reciprocal Rank Fusion**.

- **`BM25RetrievalAdapter`** (`src/retrieval/bm25_adapter.py`) — lexical retrieval
  built **in memory at startup from the Chroma collection's stored `documents`**,
  not from the source JSON. Those documents are the exact `build_document_text`
  output (with ADR-0010 synonyms), so the lexical and dense sides see identical
  text for free. The vectors are ignored. No embedder is involved, so the e5
  `"query: "` prefix is never applied — BM25 matches raw query terms. Tokenization
  is lowercase + Unicode `\w+` split (keeps `cachaça`, `750`).
- **`HybridRetrievalAdapter`** (`src/retrieval/hybrid.py`) — takes a dense and a
  lexical `RetrievalPort` and is one itself, so `ClassifyProduct` is unchanged.
  RRF score per NCM is `Σ 1/(k_rrf + rank + 1)` (rank 0-based, `k_rrf=60`, the
  standard constant — no critical hyperparameter), fused by `ncm_code`. Each
  retriever is queried for a generous pool (≥ corpus) so the rankings overlap.
- **`RetrievalMode`** (`DENSE` / `HYBRID`, env `RETRIEVAL_MODE`, **default
  `DENSE`**) selects the wiring in `build_classify_use_case`. Production stays
  dense-only with no env var; hybrid is opt-in.

**No index change.** Hybrid is a query-time composition: same vectors, same
documents, same `embedder`/`enrich_strategy` metadata. The existing index↔config
guard remains sufficient, and BM25 inherits the guarded documents (the guard
fires before BM25 is built). The returned candidate `score` is now the RRF score
(not `1 - cosine`); the confidence gate must be recalibrated against this scale
before it is read as a probability (rerank is still Passthrough, threshold a
placeholder — unchanged here).

## Measured Result

Single deterministic run, v2 (350 cases), `RETRIEVAL_MODE=hybrid` over the
synonym-enriched `tipi_capbeverage` collection. Baseline column is ADR-0010
(dense + synonyms).

### Aggregate — both v2 targets met

| Metric | ADR-0010 | Hybrid (ADR-0011) | Δ | v2 target |
|---|---|---|---|---|
| Top-1 | 30.9% (108) | **49.1% (172)** | +18.2 pp | ≥40% ✓ |
| Top-3 | 51.7% (181) | **68.0% (238)** | +16.3 pp | ≥65% ✓ |

### By mode (top-3)

| Mode | n | ADR-0010 | Hybrid | Δ pp |
|---|---|---|---|---|
| **colloquial** | 127 | 59.1% | **85.0% (108)** | **+25.9** |
| poverty | 73 | 46.6% | 60.3% (44) | +13.7 |
| negation | 30 | 43.3% | 56.7% (17) | +13.4 |
| direct | 64 | 57.8% | 68.8% (44) | +11.0 |
| multi_attr | 33 | 39.4% | 45.5% (15) | +6.1 |
| frontier | 23 | 39.1% | 43.5% (10) | +4.4 |

Top-1 rose in every mode, no regression (colloquial 44.9% → 73.2%, +36 cases).

### By answer chapter (top-3)

| Chapter | n | ADR-0010 | Hybrid | Δ pp |
|---|---|---|---|---|
| 22 (beverages) | 249 | 46.6% | **66.7% (166)** | +20.1 |
| 21 (preparations) | 36 | 72.2% | **88.9% (32)** | +16.7 |
| 20 (juices) | 65 | 60.0% | 61.5% (40) | +1.5 |

## Prediction vs Outcome

Predictions registered before measuring (CP3).

| Prediction | Outcome | Verdict |
|---|---|---|
| `multi_attr` rises from 39.4% (BM25 hits `Brix 60`, `concentrado`, `anidro`) | 39.4 → **45.5%** (+6.1) | Confirmed |
| `colloquial`: **marginal** gain over 59.1% | 59.1 → **85.0%** (+25.9) | **Underestimated** |
| `direct` rises (exact corpus terms) | 57.8 → **68.8%** (+11.0) | Confirmed |
| Aggregate top-3 **55–62%** | **68.0%** | **Above range** |
| Possible **regression** in `negation` (lexical mis-match on "sem álcool") | 43.3 → **56.7%** (+13.4) | Did not occur — RRF absorbed it |

**Why colloquial exploded (not marginal): ADR-0010 and ADR-0011 compound.**
The synonyms file put the brand *into* the document; the dense retriever still
only fuzzy-matched it. BM25 makes the **exact brand-token match decisive**
(`Johnnie Walker`, `Chivas`, `Smirnoff` → a pinned hit on the doc carrying that
synonym), and RRF fuses the two rankings. One ADR supplies the vocabulary, the
other makes it count — neither alone gets there.

**Why negation did not regress.** RRF never lets BM25 dominate alone: the dense
side keeps contributing the semantics of "sem álcool" while BM25 adds lexical
weight, and fusion summed rather than competed. The predicted risk did not
materialise.

**Why Cap 20 barely moved (+1.5).** Juice cases hinge on attribute tokens
(Brix/concentration) where the fruit already matched; the ceiling there is fine
separability between juice leaves, not vocabulary or lexical recall — a different
lever (rerank).

## Caveats

- **RRF score is not calibrated.** The candidate `score` is now an RRF sum, a
  different scale from `1 - cosine`. The confidence gate / threshold must not be
  read as a probability until recalibrated (deferred — rerank is Passthrough).
- **BM25 is rebuilt in memory each startup** from the collection documents. For
  64 docs this is sub-millisecond; no persistence, no extra guard. If the corpus
  grows by orders of magnitude this becomes a startup cost to revisit.
- **Production (v1/cap22) is untouched** — `RETRIEVAL_MODE` defaults to `DENSE`.
  Hybrid ships only on the v2 beverage corpus, opt-in.

## Path Forward

Both v2 targets are met, but headroom remains where lexical and dense both
struggle: `frontier` (43.5%), `multi_attr` (45.5%), and fine separability between
sibling juice leaves (Cap 20). **ADR-0012 — local cross-encoder rerank**
(BGE/Jina/MS-MARCO) is the next lever: re-score the fused top-k with a model that
reads query and candidate together, zero recurring API cost. ADR-0013 (LLM
rerank) stays the last resort, gated on the R$ 0.10 / 4 s budget.
