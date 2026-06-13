# ADR-0006: Subheading-Only Enrichment (Form B)

## Status
Accepted with regression — informs ADR-0007. Not promoted to production; the
baseline (`OFF`, 63.3% top-3) remains what ships. Form B is preserved behind the
`EnrichStrategy.SUBHEADING_ONLY` flag, reproducible via `make eval-subheading`.

## Context
- **ADR-0004 baseline (`OFF`):** e5-small dense retrieval, 33.3% top-1 /
  63.3% top-3.
- **ADR-0005 (`FULL`):** heading + subheading + leaf enrichment regressed top-3
  to 53.3%. Root cause: *sibling homogenization* — the wide 4-digit heading,
  injected identically into every child, collapses siblings in embedding space.
  The width of the shared injected level predicted the sign.
- **This ADR's question:** if the wide heading is the culprit, does injecting
  *only* the narrow 6-digit subheading — never the heading — recover the top-3
  ceiling while keeping the top-1 gains? This is **Form B** from the CP1
  structural investigation. The constraint was chosen deliberately: stay
  offline, free, and CI-reproducible without an API key (no LLM rerank).
- **Structural premise behind B:** the 6-digit subheading is the Harmonized
  System's *product* level; the 4-digit heading is the broad family. Inject the
  product level, never the family — a parameter-free, binary rule, so it cannot
  be tuned to the 30-case eval (anti-overfitting discipline). **Accepted cost:**
  narrow product-naming *headings* (Vermutes 22.05, fermented beverages 22.06)
  lose their term, since B never injects a heading.

## Decision (what was tested)
`build_document_text` gained `EnrichStrategy.SUBHEADING_ONLY`: when the
subheading description is substantive (`is_substantive`), compose
`"{subheading}. {leaf}"`; otherwise `"{leaf}"` alone. The heading is never
injected and there is no fallback to it. The leaf is cleaned
(`clean_level_text`) in any enrich mode; `OFF` keeps the raw leaf, byte-for-byte.
The strategy was measured **once** against the eval suite.

## Measured Result

Cell = `{top-1}{top-3} r{rank in top-10}` · `1` = top-1 hit, `3` = top-3 hit,
`.` = miss, `r-` = outside top-10.

| Case | Diff | Expected | OFF | FULL | B | B vs OFF | B vs FULL |
|---|---|---|---|---|---|:--:|:--:|
| 001 | easy | 2201.10.00 | `.3 r2` | `.. r5` | `13 r1` | = | **+++** |
| 002 | easy | 2202.10.00 | `13 r1` | `.. r6` | `13 r1` | = | **+++** |
| 003 | medium | 2201.90.00 | `.. r-` | `.. r7` | `.. r-` | = | = |
| 004 | easy | 2202.10.00 | `.. r4` | `.. r-` | `.. r7` | = | = |
| 005 | easy | 2202.10.00 | `.3 r2` | `.. r10` | `.. r4` | **REG** | = |
| 006 | medium | 2202.99.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 007 | medium | 2202.99.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 008† | hard | 2009.12.00 | `.. r-` | `.. r-` | `.. r-` | = | = |
| 009 | hard | 2202.99.00 | `.3 r2` | `.3 r2` | `.3 r2` | = | = |
| 010 | hard | 2202.99.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 011 | easy | 2203.00.00 | `.3 r2` | `13 r1` | `13 r1` | = | = |
| 012 | easy | 2203.00.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 013 | hard | 2202.91.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 014 | easy | 2204.21.00 | `.. r5` | `.. r-` | `.. r-` | = | = |
| 015 | medium | 2204.10.90 | `.. r-` | `.3 r2` | `.3 r2` | **+++** | = |
| 016 | medium | 2204.21.00 | `.3 r3` | `.. r8` | `.. r4` | **REG** | = |
| 017 | medium | 2204.22.11 | `.3 r3` | `.. r-` | `.. r5` | **REG** | = |
| 018 | easy | 2205.10.00 | `.. r-` | `13 r1` | `.. r-` | = | **REG** |
| 019 | medium | 2205.10.00 | `.. r-` | `.3 r3` | `.. r-` | = | **REG** |
| 020 | medium | 2206.00.10 | `.. r-` | `.. r5` | `.. r7` | = | = |
| 021 | medium | 2206.00.90 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 022 | hard | 2206.00.90 | `.3 r2` | `13 r1` | `13 r1` | = | = |
| 023 | hard | 2207.20.20 | `.. r-` | `.. r-` | `.. r6` | = | = |
| 024 | medium | 2207.10.90 | `.3 r2` | `.. r4` | `.. r5` | **REG** | = |
| 025 | easy | 2208.40.00 | `.. r-` | `.. r-` | `.. r-` | = | = |
| 026 | medium | 2208.30.20 | `.. r-` | `.3 r3` | `.. r8` | = | **REG** |
| 027 | easy | 2208.60.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| 028 | easy | 2208.70.00 | `13 r1` | `13 r1` | `.3 r3` | = | = |
| 029 | medium | 2208.90.00 | `.3 r2` | `.. r7` | `13 r1` | = | **+++** |
| 030 | hard | 2202.99.00 | `13 r1` | `13 r1` | `13 r1` | = | = |
| **Total** | | | **10 / 19** | **12 / 16** | **13 / 16** | | |

| Strategy | top-1 | top-3 | ECE (informative only) |
|---|---|---|---|
| OFF | 33.3% | **63.3%** | 0.540 |
| FULL | 40.0% | 53.3% | 0.467 |
| **B** | **43.3%** | 53.3% | 0.435 |

† case-008 is out-of-scope (expected NCM in Chapter 20, not 22); a miss in all
three by design.

**top-3, B vs OFF:** recovered 1 (015) · regressed 4 (005, 016, 017, 024) →
19 + 1 − 4 = **16**. B has the **best top-1 of the three (43.3%)** but ties FULL
at the rerank ceiling (53.3%), **below OFF (63.3%)**. top-1 is not the objective;
the top-3 ceiling that rerank must lift is.

> **Top-1 audit note (case-028, Licores `2208.70.00`).** 028 also dropped from
> top-1 to rank 3 under B (`OFF 13 r1 → B .3 r3`). It is a *top-1* regression,
> not a top-3 one, so it is not in the "regressed 4" count above. Recorded here
> to avoid an audit hole: cleaning the leaf shifts rankings even with no
> parent-level injection, because every document is re-embedded.

**Prediction vs outcome.** The pre-registered prediction held only in part.
*Held:* Vermutes/Sidra (018/019/020/022) stayed at their OFF rank — the conscious
sacrifice, confirmed; the water/spirit families that FULL homogenized (001/002/
029) did *not* regress under B. *Failed:* the "subheading names the product, so
it recovers" claim — only 015 recovered; case-024 (ethanol) and case-026 (the
whisky poster child) did not, and 016/017 (wines) regressed. The next section
explains why.

## Mechanism: homogenization is level-agnostic

ADR-0005 read the regression as a property of the **4-digit heading**: a wide,
generic family description, injected identically into every child, collapses
siblings in embedding space. Form B was the direct test of the *level*
hypothesis — *inject the 6-digit subheading, never the heading* — on the premise
that the subheading is the narrow "product" level.

The test refutes the level hypothesis. B lands at the **same top-3 ceiling as
FULL (53.3%)**, and its regressors expose why. Cases 016 (`2204.21.00`),
017 (`2204.22.11`) and 024 (`2207.10.90`) belong to the large wine and ethanol
families, whose injected **subheading is itself a long, generic legal
refinement** — `"Outros vinhos; mostos de uvas cuja fermentação tenha sido
impedida ou interrompida por adição de álcool"` shared verbatim across
`2204.21 / 2204.22 / 2204.29`, and `"Álcool etílico não desnaturado… ≥ 80 %"`
across `2207.10 / 2207.20`. Injected, this text behaves as a **mini-heading**:
it homogenizes the siblings exactly as the 4-digit family description did. B
failed for the same reason FULL did — only one level down.

The corrected statement: **it is the genericity (and shared width) of the
injected *text* that predicts the sign, not its position in the hierarchy.** A
short product name helps (case 015, subheading `"Vinhos espumantes e vinhos
espumosos"`, recovered from miss to rank 2); a long generic refinement hurts, at
either level.

## Self-correction of the 6-digit premise

The Form B decision rested on a structural claim from the Harmonized System: the
6-digit subheading is the internationally-defined *product* level, so injecting
it (and never the broad 4-digit family) was argued to be a parameter-free,
structurally-honest rule. That claim is **structurally motivated but empirically
false for parts of TIPI Chapter 22**. Several 6-digit subheadings here are not
product names but **legal refinements** (`"Outros vinhos; mostos…"`,
`"Álcool etílico não desnaturado…"`), while the product name lives one level
down in the leaf (`Vodca`, `Gim e genebra`) or, for whiskies, up at a *narrow*
subheading (`"Uísques"`). The HS "product at 6-digit" rule is a tendency, not an
invariant.

The honest correction is that **"level" was the wrong discriminating axis**. The
right axis is **product-name vs generic-refinement**, and `is_substantive` does
not capture it: it strips only `"Outros"`, so `"Outros vinhos; mostos…"` passes
as substantive and is injected. Separating a product name from a legal
refinement needs a discriminator we do not yet have — deferred to ADR-0007.

**Irony of case-026 (Johnnie Walker → `2208.30.20`, "Uísques").** The very case
that motivated Form B did **worse under B (rank 8) than under FULL (rank 3)**. It
is a colloquial-gap case ("Johnnie Walker" never matches "Uísques"); and under B
the sibling spirits (`Vodca`, `Rum`, `Gim`) gained distinct cleaned leaves and
out-ranked it, whereas under FULL they were all homogenized by the shared
heading, letting 026 float relatively higher. The motivating example does not
benefit from the rule it motivated.

## Consequences
- **B is not promoted.** `OFF` (63.3% top-3) remains the production baseline,
  reproduced *exactly* (byte-for-byte, including the per-difficulty breakdown)
  by the enum migration.
- B is preserved behind `EnrichStrategy.SUBHEADING_ONLY`, reproducible via
  `make eval-subheading`; `FULL` likewise stays as `make eval-full`. The
  per-case snapshot is committed at `docs/adr/assets/0006-analysis.json`.
- The index records `enrich_strategy` (a string) as collection metadata; the
  adapter raises an actionable `RuntimeError` on a strategy mismatch, including
  a legacy bool-keyed ADR-0005 index (`enrich_documents`), so a stale index
  fails loudly rather than silently.
- **CI guards only the `OFF` path** (`make index` + the default eval gate); no
  enriched tier runs in CI. CI exists to protect what ships, and what ships is
  the 63.3% baseline.

## Path Forward
- **ADR-0007 — selective enrichment with a product-name vs generic-refinement
  discriminator.** `is_substantive` is insufficient (it strips only `"Outros"`).
  Structural candidates to investigate (not chosen here):
  - **legal markers** — text starting with `"Outros"`, or containing `"cuja"`,
    `"exceto"`, `";"`, reads as a generic refinement;
  - **inter-sibling textual sharing** — text identical across N siblings is
    generic by definition (Form C; measures the cause directly);
  - **length** — with the explicit risk that it becomes a tunable parameter.

  The discriminator has more degrees of freedom than the prior rules, so it has
  **more room to overfit the 30 cases**. It must be justified by TIPI's
  linguistic/legal structure, not by the eval numbers.
- **LLM rerank is explicitly deferred on cost grounds** — keeping the system
  offline, free, and CI-reproducible without an API key — and is registered as
  the fallback if selective enrichment also fails.
- **Termination clause.** Should ADR-0007 also fail to lift the top-3 ceiling
  above OFF's 63.3%, the accumulated evidence (three negative enrichment
  results) would indicate that offline document-text manipulation cannot reach
  the v1 target, and the trade-off between the target and the cost of reranking
  would need to be revisited.

## References
- Strategy + tests: commit `240ebf1`
  (`feat(retrieval): add SUBHEADING_ONLY enrichment strategy`).
- This ADR, the `eval-full` / `eval-subheading` Makefile targets, and the
  forward note added to ADR-0005: the closing commit of this ADR.
- Data: `docs/adr/assets/0006-analysis.json` (per-case predictions, scores, ECE
  bins), generated by `scripts/analyze_eval.py` against the `SUBHEADING_ONLY`
  index (k=10 diagnostic depth).
- Predecessors: `docs/adr/0005-hierarchical-enrichment.md`,
  `docs/adr/0004-semantic-retrieval-e5-small.md`.
