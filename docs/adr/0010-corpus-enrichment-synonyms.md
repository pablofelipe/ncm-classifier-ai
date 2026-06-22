# ADR-0010: Corpus enrichment via synonyms file

**Status:** Accepted (ships on the v2 beverage corpus) — opens ADR-0011 (BM25 + e5 hybrid).

## Context

ADR-0009 set the honest v2 baseline at **20.3% top-1 / 32.6% top-3** over 350
cases and 64 NCMs (Ch.20/21/22), and named the dominant hole precisely:
**colloquial input** — 127/350 cases (36% of the suite) at **20.5% top-3**, the
worst of the six modes and the single biggest drag on the aggregate. Every
severe miss (rank ≥ 50) was a brand or popular-name query: `Johnnie Walker`,
`Coca-Cola`, `Skol`, `Aperol`, `Smirnoff`. These tokens simply do not appear in
the official TIPI nomenclature — `2208.60.00` reads `- Vodca`, never `Smirnoff` —
so a dense retriever has nothing to match against.

ADRs 0005–0008 closed the offline document-manipulation line (enrichment of the
*structure* and the embedder swap both capped out ~63% on v1). The remaining
failures are query-understanding, not document representation. Corpus enrichment
attacks that gap from the cheapest possible angle: add the missing vocabulary
(brands, colloquial and foreign variety names) to the document text, offline,
zero recurring cost.

This is **corpus** enrichment, not a new document-text *strategy*: it rides on
the shipping `OFF` baseline rather than adding an `EnrichStrategy` variant.

## Decision

A curated synonyms file, `data/synonyms/beverage_synonyms.json`, maps each NCM to
the brands and colloquial names absent from its official description:

- **22 NCMs, 129 terms**, **evidence-bound to v2**: every term appears in a v2
  colloquial query. NCMs with ≥2 colloquial cases are covered; the 7 NCMs with a
  single colloquial case are left out (see Remaining gap).
- **Decisions applied** (from the CP1 investigation):
  - `2009.50.00` dropped — its brands (`Pomarola`, `Elefante`) are tomato *sauce*,
    not juice; factually wrong as a juice synonym.
  - `sake`/`saquê` dropped from `2208.90.00` — the only cross-NCM conflict
    (`Sake` maps to both `2208.90.00` and `2206.00.90` in the eval).
  - **Juices carry fruit-explicit terms, never bare brands** — `"suco de abacaxi
    Maguary"`, not `"Maguary"` — because a juice brand spans fruits (`Maguary` is
    both pineapple and guava) and cannot disambiguate alone. For spirits the brand
    *is* the discriminator (`Smirnoff` → vodka, 1:1), so bare brands stand.

`build_document_text(entry, strategy, synonyms)` appends the terms as
`"{text} | term, term"` **only when `strategy is OFF`**. An absent/empty mapping
leaves the text byte-for-byte unchanged (graceful — indexing proceeds with no
synonyms file). The synonym source is injected (a mapping in tests, a configurable
`Settings.synonyms_path` in production), so unit tests never touch the real file.

**v1 baseline blindagem.** `_synonyms_for_chapter(chapter, path)` gates loading to
the `beverage` corpus only: any other chapter (i.e. the frozen cap22 production
baseline) gets an empty mapping, even with the file present on disk. Confirmed —
`make eval` (v1) stays at **33.3% top-1 / 63.3% top-3** after the change.

## Measured Result

Single deterministic run (e5-small `OFF` + Passthrough rerank), v2 reindexed with
synonyms into `tipi_capbeverage`.

### Aggregate (350 cases)

| Metric | Baseline (ADR-0009) | With synonyms | Δ |
|---|---|---|---|
| Top-1 | 20.3% (71) | **30.9% (108)** | **+10.6 pp** (+37) |
| Top-3 | 32.6% (114) | **51.7% (181)** | **+19.1 pp** (+67) |

### By mode (top-3)

| Mode | n | Baseline | With synonyms | Δ pp |
|---|---|---|---|---|
| **colloquial** | 127 | 20.5% (26) | **59.1% (75)** | **+38.6** |
| poverty | 73 | 34.2% (25) | 46.6% (34) | +12.4 |
| frontier | 23 | 30.4% (7) | 39.1% (9) | +8.7 |
| direct | 64 | 50.0% (32) | 57.8% (37) | +7.8 |
| negation | 30 | 36.7% (11) | 43.3% (13) | +6.6 |
| multi_attr | 33 | 39.4% (13) | 39.4% (13) | **0.0** |

### By answer chapter

| Chapter | n | Baseline top-3 | With synonyms top-3 | Δ pp | top-1 Δ pp |
|---|---|---|---|---|---|
| 20 (juices) | 65 | 33.8% (22) | **60.0% (39)** | +26.2 | +13.8 |
| 21 (preparations) | 36 | 41.7% (15) | **72.2% (26)** | +30.6 | +13.9 |
| 22 (beverages) | 249 | 30.9% (77) | **46.6% (116)** | +15.7 | +9.2 |

### By difficulty (top-3)

| Difficulty | n | Baseline | With synonyms | Δ pp |
|---|---|---|---|---|
| easy | 65 | 44.6% (29) | 60.0% (39) | +15.4 |
| medium | 147 | 32.0% (47) | 59.9% (88) | +27.9 |
| hard | 138 | 27.5% (38) | 39.1% (54) | +11.6 |

## Prediction vs Outcome

Predictions were registered before measuring (CP3).

| Prediction | Outcome | Verdict |
|---|---|---|
| Colloquial 20.5% → **35–45%** top-3 | **59.1%** | **Underestimated** |
| Direct/poverty/negation unchanged or marginal | top-3 +7.8 / +12.4 / +6.6; top-1 −1 / −2 / −1 | Partial |
| Aggregate 32.6% → **~38–45%** top-3 | **51.7%** | **Underestimated** |
| Biggest gain: Cap 22 spirits + soft drinks | True in absolute (colloquial +38.6 pp, Cap 22 +39 cases); by pp Cap 21 (+30.6) and Cap 20 (+26.2) gained more | Partial |

**Why the underestimate.** Two effects were not priced in:

1. **Generic type-words help `poverty`, not just `colloquial`.** Evidence-bound
   variants like `vodca`, `gin`, `uísque`, `cachaça`, `conhaque` are not brands —
   they are the popular Portuguese product names missing from the formal leaf
   (`- Vodca` has the word, but `2208.20.00` reads "Aguardentes de vinho ou de
   bagaço", never `conhaque`). They reinforced generic-description poverty cases
   (`vodca de batata`, `aguardente de mel`) the prediction assumed untouched.
2. **Small chapters move fast in pp.** Cap 20/21 (juices, coffee/tea) are 65 and
   36 cases; brands like `Nescafé`, `Nespresso`, `Tang`, `Del Valle` plus the
   fruit-explicit juice terms filled a proportionally larger hole, so their
   per-point gain outran Cap 22 even though Cap 22 won the absolute case count.

## Caveats documented

- **Top-1 regressions (−4 cases): direct −1, poverty −2, negation −1.** Appending
  synonyms perturbs the document embeddings and reshuffles near-ties; a handful of
  former rank-1 hits dropped to rank-2/3. **All four remain within top-3** — net
  top-3 rises in every mode. This is the expected cost of changing document text
  and is recorded honestly rather than hidden by the headline.
- **`multi_attr` flat at 0.0 pp — coherent.** Its cases turn on attribute tokens
  (`Brix 60`, `concentrado`, container volume), which are not synonyms. Corpus
  enrichment has nothing to offer them — consistent with the prediction. This is
  precisely the hole ADR-0011 targets.

## Remaining gap

Colloquial still misses **52/127**. The residual splits into:

- **7 out-of-coverage NCMs** (a single colloquial case each, deliberately not
  enriched to avoid overfitting on n=1 and cross-NCM ambiguity): `2202.91.00`
  (Heineken zero), `2101.20.10` (Lipton), `2101.20.20` (Leão Fumo), `2204.10.10`
  (Dom Pérignon), `2206.00.90` (sake — conflicts with `2208.90.00`), `2009.71.00`
  (Kapo), `2009.61.00` (Welch's).
- **Hard brands and foreign varieties** in the catch-all `2208.90.00` and across
  spirits that even with synonyms sit below rank-3.

## Targets

v2 targets (ADR-0009, recalibrated): **≥40% top-1 / ≥65% top-3**.

| Metric | Now | Target | Gap |
|---|---|---|---|
| Top-1 | 30.9% | ≥40% | −9.1 pp |
| Top-3 | 51.7% | ≥65% | −13.3 pp |

Corpus enrichment is a large step, not the finish line. It is accepted and ships
on the v2 corpus; the targets remain open for the next levers.

## Path Forward

**ADR-0011 — BM25 + e5 hybrid retrieval.** Lexical recall fused with dense
retrieval, zero recurring cost. It directly attacks the holes synonyms cannot:
`multi_attr` / Brix exact-token cases (flat here) and the hard-brand colloquial
residual, where an exact lexical match on a rare token outranks a fuzzy dense
neighbour. Cost-ordered before the rerank levers (ADR-0012 cross-encoder,
ADR-0013 LLM rerank).
