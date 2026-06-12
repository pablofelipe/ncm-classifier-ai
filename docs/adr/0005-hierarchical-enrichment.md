# ADR-0005: Hierarchical Document Enrichment

## Status
Accepted with regression — informs ADR-0006. Not promoted to
production; preserved behind the `ENRICH_DOCUMENTS` flag (default off).

## Context

ADR-0004 measured the e5-small semantic baseline (top-1 33.3%, top-3
63.3%) and identified **TIPI text poverty** as the dominant error mode
(13/20 top-1 misses, 65%): 8-digit descriptions are written relative to
their parent heading, and `build_document_text` indexed them without
that context — "vinho" absent from 2204.21.00, "vermute" from
2205.10.00, "uísque" from 2208.30.20.

Working hypothesis: prepending the parent heading and subheading
descriptions to each document closes the gap. The prediction was
**recorded before measuring** (this ADR reports prediction vs outcome
honestly).

## Decision (what was tried)

Extend ingestion to capture, per NCM, the cleaned `heading_description`
and `subheading_description` (general → specific chain, empty "Outros"
levels skipped). `build_document_text` composes
`"{heading}. {subheading}. {description}"`, skipping empty fields and
stripping the "-- " level markers. Rerank stays Passthrough; the
embedder, the pinned revision, and the `passage:` prefix are unchanged
from ADR-0004 — enrichment is the single isolated variable.

## Measured Result — net regression

Eval set: `eval/v1_cases.json` (30 cases). Index: 34 Chapter 22 entries,
TIPI Decreto 11.158/2022 (consolidado em 08/06/2026).

| Metric | ADR-0004 (enrich off) | Enriched | Δ | v1 target |
|---|---|---|---|---|
| Top-1 | 10/30 = 33.3% | 12/30 = 40.0% | +6.7 pp | ≥ 70% ✗ |
| Top-3 | 19/30 = 63.3% | 16/30 = 53.3% | **−10.0 pp** | ≥ 90% ✗ |
| Rerank ceiling (top-3) | 63.3% | **53.3%** | −10.0 pp | — |
| Attractor 2208.30.10 (wrong top-2) | 10 | 0 | −10 | — |

The top-1 gain is real but marginal against the loss of top-3 and, more
importantly, the **rerank ceiling**: a perfect reranker over enriched
retrieval caps at 16/30 = 53.3%, *below* the 63.3% the baseline already
offered. Enrichment moves the system *away* from the v1 target it must
eventually reach through reranking.

ECE shifted 0.54 → 0.47, but this is **not meaningful** — scores remain
uncalibrated and statistically indistinguishable between hits and misses
(ADR-0004).

### Per-case comparison

Rank = position of the expected NCM in the retrieval list (`>10` =
outside top-10). Family (n) = NCMs under that heading in the index.
Full per-case data: `docs/adr/assets/0005-analysis.json`.

| Case | Family (n) | Expected | Before | After | Verdict | Mode |
|---|---|---|---|---|---|---|
| 001 | 22.01 (2) | 2201.10.00 | 2 | 5 | ↓ regress | negation |
| 002 | 22.02 (3) | 2202.10.00 | 1 | 6 | ↓ lost top-1 | (was hit) |
| 003 | 22.01 (2) | 2201.90.00 | >10 | 7 | ↑ improve | poverty |
| 004 | 22.02 (3) | 2202.10.00 | 4 | >10 | ↓ regress | colloquial |
| 005 | 22.02 (3) | 2202.10.00 | 2 | 10 | ↓ regress | negation |
| 006 | 22.02 (3) | 2202.99.00 | 1 | 1 | = | hit |
| 007 | 22.02 (3) | 2202.99.00 | 1 | 1 | = | hit |
| 008 | ch.20 (—) | 2009.12.00 | >10 | >10 | = | frontier † |
| 009 | 22.02 (3) | 2202.99.00 | 2 | 2 | = | frontier † |
| 010 | 22.02 (3) | 2202.99.00 | 1 | 1 | = | hit |
| 011 | 2203 (1) | 2203.00.00 | 2 | 1 | ↑ new hit | negation |
| 012 | 2203 (1) | 2203.00.00 | 1 | 1 | = | hit |
| 013 | 22.02 (3) | 2202.91.00 | 1 | 1 | = | hit |
| 014 | 22.04 (9) | 2204.21.00 | 5 | >10 | ↓ regress | poverty |
| 015 | 22.04 (9) | 2204.10.90 | >10 | 2 | ↑ improve | poverty |
| 016 | 22.04 (9) | 2204.21.00 | 3 | 8 | ↓ regress | poverty |
| 017 | 22.04 (9) | 2204.22.11 | 3 | >10 | ↓ regress | poverty |
| 018 | 22.05 (2) | 2205.10.00 | >10 | 1 | ↑ new hit | poverty |
| 019 | 22.05 (2) | 2205.10.00 | >10 | 3 | ↑ improve | poverty |
| 020 | 2206 (2) | 2206.00.10 | >10 | 5 | ↑ improve | poverty |
| 021 | 2206 (2) | 2206.00.90 | 1 | 1 | = | hit |
| 022 | 2206 (2) | 2206.00.90 | 2 | 1 | ↑ new hit | poverty |
| 023 | 22.07 (5) | 2207.20.20 | >10 | >10 | = | poverty |
| 024 | 22.07 (5) | 2207.10.90 | 2 | 4 | ↓ regress | poverty |
| 025 | 22.08 (9) | 2208.40.00 | >10 | >10 | = | colloquial (cachaça) |
| 026 | 22.08 (9) | 2208.30.20 | >10 | 3 | ↑ improve | poverty |
| 027 | 22.08 (9) | 2208.60.00 | 1 | 1 | = | hit |
| 028 | 22.08 (9) | 2208.70.00 | 1 | 1 | = | hit |
| 029 | 22.08 (9) | 2208.90.00 | 2 | 7 | ↓ regress | poverty |
| 030 | 22.02 (3) | 2202.99.00 | 1 | 1 | = | hit |

† Frontier cases are invariant across both regimes and count as
evidence neither for nor against enrichment: case-008 is structurally
unreachable in v1 (the index covers Chapter 22 only; its answer is in
Chapter 20), and case-009 is a Chapter 20/22 boundary case that ranks
identically (2) under both.

## Prediction vs Outcome (honest)

The prediction failed instructively:

- **TIPI text poverty (13 predicted to improve):** 7 improved, 5
  regressed, 1 unchanged. The hypothesis held precisely where the term
  was *absent* (Martini → 2205 rank 1, Aperol → 3, Johnnie Walker → 3,
  sidra → 5) and failed for bottled wine (014, 016, 017) and large
  generic families (024, 029).
- **Negation / colloquial (predicted unchanged):** wrong in both
  directions — 011 improved (new hit) and 001/004/005 regressed, all
  through the single mechanism below. Only 025 (cachaça) stayed put.
- **Attractor 2208.30.10:** predicted to lose its pull, and it did —
  wrong top-2 appearances 10 → 0. The only prediction fully confirmed.

## Root Cause — sibling homogenization

The injected heading is the longest and most semantically loaded
component of every enriched document, and it is *identical* across all
NCMs under the same heading. After enrichment, each document's embedding
is dominated by this shared mass, so sibling documents collapse toward
the same point in vector space. The short, specific tail — the entry's
own description, the only thing distinguishing siblings — is outweighed.
Ranking *within* a family is then decided by small tail differences that
rarely align with the query's real discriminators (grape, brand, pack
size as an e-commerce shopper writes them, not the TIPI legal tail). The
sibling whose tail least *dilutes* the shared heading wins the whole
family.

**The dividing line is the level and width of sharing, not the declared
difficulty.** Enrichment is a net win when a parent supplies a
*product-identity noun that was absent* and the sharing is narrow:
vermouth (22.05, 2 children, heading names "Vermutes" → 018/019), sidra
(2206, 2 children → 020/022). It is a net loss when a *heading* shared
by a large family injects a noun the query already wants — "Vinhos"
across all 9 children of 22.04, the water vocabulary across 22.02 —
collapsing the discriminator. The regressions cluster in the two largest
families (22.04 and 22.08, 9 children each) and the water-heavy 22.02;
the wins cluster in the 2-child families.

**The discriminating level matters, not just family size.** Within a
large family, a narrow subheading still helps: case-026 (Johnnie Walker,
22.08 / 9 children) improved >10 → 3 because the gain came from
subheading 2208.3 ("Uísques", shared by only 3 packaging-distinct
children), not from the generic 22.08 heading. The harm comes from wide
heading sharing; narrow subheading sharing can still discriminate.

Concretely, **2204.30.00** ("Outros mostos de uvas" — a near-pure-heading
document) became top-1 for *every* wine query (014, 016, 017): the
correct **2204.21.00** carries a packaging tail ("Em recipientes não
superior a 2 l") that pushes it *away* from a query about grape and
vintage, while the short "Outros mostos" tail barely perturbs the
heading. Symmetrically, **2202.91.00** ("Cerveja sem álcool") became an
attractor for water and soft-drink queries (001, 002, 005), flooded by
the 22.02 heading "águas… açúcar… edulcorantes… bebidas não alcoólicas".

**The double irony of case-011 is the proof of the mechanism.** Before
enrichment, "cerveja puro malte" stuck to the literal string "Cerveja
sem álcool" (2202.91.00). After enrichment, that same string was diluted
by the water-heavy 22.02 heading, so the query detached and moved to
**2203.00.00** ("Cervejas de malte") — which stayed clean *precisely
because the 2203 position has no heading row to inject*. Enrichment
fixed 011 for the very same reason it broke 002. We traded one global
attractor (2208.30.10, neutralized 10 → 0) for family-local attractors
(2204.30.00, 2202.91.00).

## Decision on the code

The enrichment is **preserved behind a config flag**, not reverted and
not promoted:

- `ENRICH_DOCUMENTS` (default `False`). `build_document_text` and
  `index_entries` take an explicit `enrich` parameter (no default — a
  conscious choice at every call site); the composition root reads
  `settings.enrich_documents`.
- The index records `enrich` as collection metadata; the adapter
  validates that the configured flag matches the index it was built
  with, raising an actionable `RuntimeError` on mismatch or on a legacy
  index missing the key (loud failure, never a silent `None == False`).
- Production keeps the ADR-0004 baseline (33.3% / 63.3%), reproduced
  *exactly*, byte-for-byte including the per-difficulty breakdown.
- The experiment is reproducible via `make eval-enriched`
  (`ENRICH_DOCUMENTS=1` drives both the index strategy and the adapter's
  expected flag), with the snapshot preserved at
  `docs/adr/assets/0005-analysis.json`.

**CI guards only the production path.** The `eval.yml` workflow runs
`make index` (enrich off) and the default eval gate; it does *not* run
`eval-enriched`. Reproducibility of the negative experiment lives in the
local target plus the committed snapshot, not in CI — CI exists to
protect what ships, and what ships is the 63.3% baseline.

## Consequences

Positive:
- The dominant ADR-0004 error mode (absolute text poverty) is genuinely
  curable: where a parent supplies a missing product noun under narrow
  sharing, retrieval improves sharply (four new reachable cases,
  including two new top-1 hits among the previously unreachable).
- The global attractor 2208.30.10 is neutralized.
- The flag + index-metadata guard make the two regimes switchable and
  mutually exclusive without risk of an index/config desync going
  unnoticed.

Negative:
- Naive enrichment is a **net regression** (top-3 and rerank ceiling
  63.3% → 53.3%) and must not ship as implemented.
- It trades a global attractor for family-local ones; large families
  (22.04, 22.08) and vocabulary-heavy headings (22.02) regress.
- Confidence scores remain uncalibrated (unchanged from ADR-0004).

## Path Forward (candidates for ADR-0006, not decided here)

Each is a separate ADR with an eval delta measured against the restored
default baseline (63.3%):

- **Selective enrichment by sharing width** — inject a parent level only
  when it is shared narrowly (e.g. a product-naming subheading with ≤ N
  children), never a wide heading. Directly targets the dividing line
  this ADR identified; case-026 is the existence proof that narrow
  sharing helps.
- **Token-mass rebalancing** — counter heading dominance by weighting or
  repeating the specific tail so siblings stay separable in vector
  space.
- **LLM rerank for intra-family disambiguation** — let a reranker break
  the sibling ties the dense encoder cannot, applied on top of the
  baseline retrieval rather than the enriched one.

## References

- Commits: `33606e7` (ingest enrichment), `a68af97` (document
  composition), `456250d` (config flag + index/adapter guard).
- Data: `docs/adr/assets/0005-analysis.json` (per-case predictions,
  scores, ECE bins); generated by `scripts/analyze_adr0004.py` — the
  script is reused as-is for this ADR; its name is a leftover from
  ADR-0004 (rename deferred to a future cleanup).
- Predecessor: `docs/adr/0004-semantic-retrieval-e5-small.md`.
