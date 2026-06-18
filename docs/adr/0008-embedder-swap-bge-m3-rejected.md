# ADR-0008: Embedder Swap to bge-m3 (Rejected)

## Status
Rejected (bge-m3 swap) — **closes the offline retrieval-quality line** and opens
LLM reranking (ADR-0009). No production change: e5-small `OFF`
(33.3% top-1 / 63.3% top-3) remains the baseline and what ships. The bge-m3
infrastructure (configurable embedder, dual guard) is kept; only the swap is
rejected.

## Context
ADR-0007's root finding was that the bottleneck is the embedder's discriminative
power between siblings, not missing document context. The cost ladder ordered the
candidates by recurring cost and put **bge-m3** first: offline, zero recurring
cost, strong multilingual coverage in Portuguese, retrieval-trained. The
hypothesis: a stronger embedder crosses the v1 target without any recurring cost,
attacking the root instead of the surface.

## Decision (what was tested)
bge-m3 dense, loaded via sentence-transformers (Transformer → CLS pooling →
Normalize), **no prefix on either side** — the model card states verbatim that
bge-m3 "no longer requires adding instructions to the queries", and its config
declares no prompt; it is symmetric, unlike e5's asymmetric `query: `/`passage: `.
Revision `5617a9f6` pinned, dim 1024, dense-only (the sparse/ColBERT heads are not
part of the ST pipeline and never activate). Isolated variable: e5-dense →
bge-dense.

A single a-priori follow-up was then measured: **bge + FULL** enrichment. The
rationale was structural, not a grid sweep — bge separates siblings (which e5
collapsed), so enrichment's homogenization *might* be tolerable under bge where it
was not under e5. One combination, one measurement.

## Measured Result — full offline matrix (top-1 / top-3)

| Config | top-1 | top-3 |
|--------|-------|-------|
| **e5 OFF** (baseline, ships) | 33.3% | **63.3%** |
| e5 FULL (ADR-0005) | 33.3% | 53.3% |
| e5 SUBHEADING (ADR-0006) | 43.3% | 53.3% |
| bge OFF | 26.7% | 43.3% |
| bge FULL | 30.0% | 53.3% |

- bge OFF **regressed −20 pp top-3** versus e5 OFF.
- bge FULL recovered to 53.3% but **did not cross 63.3%** — it landed on the exact
  same ceiling as all three enrichment configurations.

Per-case snapshots for both bge runs: `docs/adr/assets/0008-analysis.json`.

## Prediction vs Outcome (honest)
- **Prediction 1** (bge swap crosses ~70%): **false**. bge OFF regressed. Cause:
  the interaction of bge with the impoverished `OFF` corpus — the raw leaf carries
  no product name (it lives in the heading, which `OFF` omits), and bge without a
  prefix anchors on short strong tokens ("Vodca", "Cerveja sem álcool"), which
  become attractors that swallow the sibling gains.
- **Prediction 2** (under bge+FULL the sibling separation survives enrichment):
  **false**. `case-016` — a sibling that **bge OFF** ranked **1** — fell to >10
  under FULL. Enrichment's homogenization hurts bge too.
- **Confirmed** ADR-0007's root finding in the detail: bge **does** separate the
  large-family siblings that e5 collapsed (`case-014` r5→1, `case-016` r3→1 under
  bge OFF). The stronger embedder helps exactly where the diagnosis predicted —
  but the gain survives neither the raw corpus (attractors) nor enrichment
  (homogenization).

## Root finding (consolidates ADRs 0005–0008)
Four enrichment experiments converge on a single top-3 ceiling of 53.3%; two
embedders converge on an offline ceiling of ~63%. **Offline manipulation — of the
document text *or* of the embedder — is exhausted.** The remaining failures split
into two kinds that no offline change addresses:

- **(a) query-understanding gap** — colloquial/brand input (`case-004` Coca-Cola,
  `case-025` cachaça): the query uses a term no document or embedder matches.
- **(b) ranking precision** — tie-breaking among correct candidates already in the
  top-k.

Both are **query/ranking** problems, not document-representation problems. e5 OFF
(63.3%) remains unbeaten offline and is what ships.

## Consequences
- **bge-m3 rejected as a production swap.** e5-small OFF stays the baseline.
- **The infrastructure is preserved and has value:** a configurable embedder
  (`EmbedderModel` enum + `make_embedding_function` factory), the
  `EmbeddingFunction` Protocol, `BGEEmbeddingFunction`, and a dual
  embedder×index guard (the embedder is recorded in collection metadata next to
  `enrich_strategy`; the adapter refuses a mismatch, embedder first). bge is
  selectable via `EMBEDDER=bge_m3` for future experiments; the default is e5.
- **Isolated win recorded:** `case-026` (Johnnie Walker) — the high-value
  colloquial case that already failed in ADR-0007 — is finally cracked by bge+FULL
  (rank 2), proving colloquial-via-product-name-in-document is solvable, but not at
  an acceptable cost in the aggregate.
- The `run_eval.py` evaluation banner now reports the live embedder and enrich
  strategy from settings (it was hardcoded to "e5-small").

## Path Forward
**ADR-0009 = LLM rerank** (cost ladder, step 3). Justification: the remaining
failures are query-understanding (a) and ranking (b) — exactly what reranking
attacks and exactly what offline retrieval provably does not touch. Take the top-k
of e5 OFF (the 63.3% ceiling) and reorder it with an LLM that understands
colloquial input (Johnnie Walker = whisky = "Uísques") and negation. This carries
a **recurring per-query cost** against the CLAUDE.md budget (R$ 0.10 / 4 s), so the
rerank ADR must measure cost and latency, not only accuracy. Recalibrating the v1
target stays as the fallback if the rerank cost is unacceptable.

Gemini `text-embedding-004` (cost ladder step 2, one-time cost) is **not** pursued:
the offline-embedding prior is now weak — bge-m3, a top multilingual retrieval
model, regressed — and the remaining failures are not in the embedding space.

## References
- Predecessors: `docs/adr/0004-semantic-retrieval-e5-small.md` (e5 chosen, bge-m3
  deferred), `0005-hierarchical-enrichment.md`, `0006-subheading-only-enrichment.md`,
  `0007-selective-enrichment-rejected.md` (root finding, cost ladder).
- Data: `docs/adr/assets/0008-analysis.json` (per-case bge OFF and bge FULL),
  `docs/adr/assets/0004-analysis.json` (e5 OFF baseline).
