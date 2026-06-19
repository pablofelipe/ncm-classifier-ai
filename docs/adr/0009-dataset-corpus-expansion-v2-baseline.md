# ADR-0009: Dataset + Corpus Expansion, v2 Baseline

## Status
Accepted — establishes the v2 baseline and recalibrated targets; opens corpus
enrichment (ADR-0010). No production change: e5-small `OFF` still ships, and CI
keeps gating on v1. v2 is local-only (`make eval-v2`).

## Context
The v1 eval set (30 cases, Chapter 22, name + rich description) reported 63.3%
top-3 — an **optimistic metric by design**: a single chapter, a small sample, and
queries carrying a full product description. ADR-0005–0008 exhausted the offline
investigation (document enrichment and embedder swap both capped at ~63% / 53%),
and the root finding pointed at query-understanding and ranking, not document
representation.

The cost-ordered roadmap that ADR-0008 opened (enrichment → hybrid → cross-encoder
→ LLM rerank) cannot be trusted on a 30-case set: deltas of one or two cases are
noise, and the set has no axis that isolates *why* a case fails. Before spending any
of the roadmap's levers, the measurement surface had to be widened and given real
statistical power and a failure-mode taxonomy.

## Decision
Expand dataset and corpus simultaneously, in one move, so the harder corpus and the
harder cases are measured together from the first v2 number:

- **Dataset v2** — 350 cases (vs 30), spanning Chapters 20/21/22, each tagged with
  one of six **failure modes** (`direct` / `colloquial` / `poverty` / `negation` /
  `frontier` / `multi_attr`) that name the query-understanding gap a case probes.
  A separate `EvalCaseV2` / `EvalSuiteV2` schema; `run_eval` auto-detects v1 vs v2
  by the `corpus_chapters` key.
- **Corpus expansion** — 64 NCMs (vs 34): Chapter 22 whole + Chapter 20 heading
  2009 (juices) + Chapter 21 partial (2101 coffee/tea extracts + 2106.90.10
  beverage preparations). One curated file, `data/tipi/tipi_beverage_20260618.json`,
  indexed into an isolated `tipi_capbeverage` collection.
- **v1 preserved intact** for retroactive comparison across ADR-0003–0008.
- **CI stays on v1**; v2 runs locally via `make eval-v2` / `make index-v2`.

This ADR records the **first v2 measurement** as the baseline. No retrieval change
is made here — only the measurement surface.

## Measured Result — v2 baseline (e5-small `OFF`, 350 cases, Passthrough rerank)

Cross-validation OK (350/350 expected_ncm present in the 64-NCM corpus).

| Aggregate | top-1 | top-3 |
|---|---|---|
| **All (350)** | 71 = **20.3%** | 114 = **32.6%** |

By difficulty:

| Difficulty | n | top-1 | top-3 |
|---|---|---|---|
| easy | 65 | 19 (29.2%) | 29 (44.6%) |
| medium | 147 | 32 (21.8%) | 47 (32.0%) |
| hard | 138 | 20 (14.5%) | 38 (27.5%) |

By mode:

| Mode | n | top-1 | top-3 |
|---|---|---|---|
| direct | 64 | 21 (32.8%) | 32 (**50.0%**) |
| multi_attr | 33 | 5 (15.2%) | 13 (39.4%) |
| negation | 30 | 6 (20.0%) | 11 (36.7%) |
| poverty | 73 | 19 (26.0%) | 25 (34.2%) |
| frontier | 23 | 4 (17.4%) | 7 (30.4%) |
| colloquial | 127 | 16 (12.6%) | 26 (**20.5%**) |

By answer chapter:

| Chapter | n | top-1 | top-3 |
|---|---|---|---|
| 20 (juices) | 65 | 15 (23.1%) | 22 (33.8%) |
| 21 (preparations) | 36 | 12 (33.3%) | 15 (41.7%) |
| 22 (beverages) | 249 | 44 (17.7%) | 77 (30.9%) |

Rank distribution over the full 64-NCM corpus (exact rank per case, k=64):

| rank 1 | 2–3 | 4–10 | >10 | not found |
|---|---|---|---|---|
| 71 | 43 | 58 | **178** | 0 |

Half the cases (178/350) rank beyond 10. No case falls outside the corpus.

ECE is **not reported**: the pipeline exposes `1 − cosine distance`, which is not a
calibrated probability (rerank is still Passthrough). Calibration waits for a real
rerank stage, as planned.

## Sanity check — Cap 22 v2 (30.9%) vs v1 (63.3%)
Chapter 22 dropped from 63.3% top-3 (v1) to 30.9% (v2) — less than half. This is the
headline number and it is **not an indexing bug**: cross-validation is OK, the index
is confirmed e5-small `OFF`, and Chapter 22 still holds the same 34 NCMs. The drop is
genuine and has three additive causes:

1. **Cross-chapter distractors.** A Chapter 22 query now competes against 64 entries,
   not 34; juices (Ch.20) and preparations (Ch.21) enter the top-k and push the
   correct answer down (visible in `frontier` cases).
2. **A much harder mix.** The 249 Chapter 22 v2 cases are saturated with brand /
   colloquial input (Johnnie Walker, Coca-Cola, Skol, Aperol) — a category almost
   absent from the 30 v1 cases.
3. **A poorer query.** v2 sends only the short name (`description=""`); v1 sent name
   **plus description**, i.e. more signal for e5.

The v1 63.3% was optimistic by design (one chapter, small sample, rich queries). The
v2 number is the honest metric, and exposing it is the point of this ADR.

## Key findings
1. **Colloquial is the dominant hole.** 127/350 cases (36%), 20.5% top-3 — and it
   drags the aggregate. Every severe miss (rank ≥ 50) is a brand/colloquial case
   (Johnnie Walker r50, Jack Daniel's r50, Coca-Cola r56, Perrier/San Pellegrino
   r64). The query uses a term no document contains. The lever is **corpus
   enrichment** (brands, synonyms — ADR-0010), not another embedder.
2. **multi_attr / Brix (mostly Cap 20).** Exact tokens — "Brix 60", "concentrado",
   "anidro 99,5%" — that dense retrieval blurs by semantic diffusion (the Brix-60/65/68
   concentrates all land rank 56–60). The lever is **lexical recall fused with
   dense** (BM25 + e5 — ADR-0011).
3. **The cross-chapter distractor effect is real but secondary** to the mix and the
   query sparsity — it shifts ranks within the top-k more than it creates new misses.

## New v2 targets (recalibrated)
The v1 targets (≥70% top-1 / ≥90% top-3) were set for 30 easy, single-chapter,
rich-query cases and are not meaningful on v2. The v2 targets are set against this
baseline as the bar the roadmap must clear:

| Metric | v2 baseline | v2 target |
|---|---|---|
| Top-3 accuracy | 32.6% | **≥ 65%** |
| Top-1 accuracy | 20.3% | **≥ 40%** |

The v1 targets remain on record for the frozen v1 set; they are not retired, only
scoped to v1.

## Prediction vs Outcome (honest)
Predictions were pre-registered before the run:

- **Cap 22 ≈ 63% (same order of magnitude as v1): false.** Dropped to 30.9% — the
  combined distractor + difficulty + short-query effect was underestimated.
- **Cap 20 juices below 50%: true** (33.8%).
- **Cap 21 above 60%: false.** Landed at 41.7% — the 7 NCMs are less separable than
  predicted ("Nespresso", "erva-mate chimarrão", "extrato de café concentrado" all
  rank 12–33).
- **Worst mode colloquial: true** (20.5%, the dominant hole); frontier (30.4%) is
  near the bottom but not the worst.
- **Best mode direct: true** (50.0%).

## Path Forward
Unchanged in order from ADR-0008; this baseline now tells us which lever attacks
which hole, and the modes give a per-bucket delta to trust each step:

- **ADR-0010 — Corpus enrichment.** Commercial descriptions, synonyms, and brand
  names attached to leaves — attacks `colloquial` (20.5% top-3, the largest hole),
  offline and cheap.
- **ADR-0011 — Hybrid retrieval (BM25 + e5).** Lexical recall for exact tokens —
  attacks `multi_attr` / Brix; zero recurring cost.
- **ADR-0012 — Local cross-encoder rerank (BGE / Jina / MS-MARCO).** The
  ranking-precision lever; zero recurring API cost.
- **ADR-0013 — LLM rerank (last resort).** Only if the above fall short; must clear
  the R$ 0.10 / 4 s budget, not only accuracy.

## References
- Data: `eval/v2_cases.json` (350 cases), `data/tipi/tipi_beverage_20260618.json`
  (64 NCMs), `eval/schema.py` (`EvalCaseV2` / `EvalSuiteV2`).
- Integration commits: `24d9f44` (v2 dataset + schema), `c80538f` (corpus + make
  targets).
- Predecessor: `docs/adr/0008-embedder-swap-bge-m3-rejected.md` (closed the offline
  line, opened this roadmap).
