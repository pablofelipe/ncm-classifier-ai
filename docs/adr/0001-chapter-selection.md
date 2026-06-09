# ADR-0001 — Chapter Selection for v1

**Status:** Accepted  
**Date:** 2026-06-08

## Context

v1 is scoped to a single NCM chapter to keep the search space bounded (30–150 codes), allow a 30-item labeled eval set to be built quickly, and deliver a deployable demo in 4 weeks. The chapter needs to satisfy:

- 30–150 NCM codes (bounded but non-trivial)
- Common in real Brazilian catalogs
- Public product examples easy to source for the eval set
- Author able to validate eval labels without external expert

Candidates evaluated:

| Chapter | Domain | Approx. codes | Notes |
|---------|--------|---------------|-------|
| Cap. 22 | Bebidas, líquidos alcoólicos e vinagres | ~40 | Author domain expertise in F&B |
| Cap. 33 | Produtos de perfumaria / cosméticos | ~60 | Good variability; no domain edge |
| Cap. 64 | Calçados | ~50 | Common; material distinctions are subtle |
| Cap. 95 | Brinquedos e jogos | ~80 | Common; possibly too dependent on images |
| Cap. 39 | Plásticos | 200+ | Too broad for v1 |

## Decision

**Capítulo 22 — Bebidas, líquidos alcoólicos e vinagres.**

## Rationale

1. **Human validation of the eval set**: the author works in the Food & Beverage domain and can verify that a labeled NCM is correct without relying on external validators. This is critical to the evaluation-first discipline: if the ground truth is wrong, all metrics are wrong.

2. **High lexical variability between close codes**: "suco", "néctar", "refresco", "bebida mista", "bebida gaseificada" map to different NCMs despite superficial similarity. This makes the task genuinely hard for lexical heuristics and a good stress test for the RAG retrieval step.

3. **Real fiscal value**: beverages are high-volume in retail NF-e data, so public SEFAZ samples will yield enough labeled examples without manual sourcing.

4. **Bounded code count**: Cap. 22 has roughly 40 active NCMs — enough to require non-trivial retrieval, small enough that the eval set covers a meaningful fraction.

## Alternatives Considered

- **Cap. 33 (cosméticos)**: good candidate, but no author domain edge for eval validation; rejected in favor of 22.
- **Cap. 64 (calçados)**: material-based distinctions (leather vs. synthetic vs. textile) may require product attributes not present in a short text description; deferred.
- **Cap. 95 (brinquedos)**: high dependency on visual product characteristics; may under-perform on text-only input; deferred to v2 if image input is added.

## Consequences

- `eval/v1_cases.json` will contain 30 products from Cap. 22 with verified NCM codes
- TIPI data ingestion (`data/tipi/`) must extract Cap. 22 entries for ChromaDB indexing
- The chapter filter is hardcoded in v1; multi-chapter routing is a v2 concern
- Success metrics apply specifically to Cap. 22; generalization to other chapters is not claimed
