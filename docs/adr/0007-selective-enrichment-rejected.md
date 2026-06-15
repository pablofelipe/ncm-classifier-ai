# ADR-0007: Selective Enrichment via Product-vs-Refinement Discriminator (Form C)

## Status
Rejected (not implemented) — **closes the enrichment line** and opens a
retrieval-quality investigation. No production change: `OFF`
(33.3% top-1 / 63.3% top-3) remains the baseline and what ships. Form C was
never coded or measured; the decision rests on the CP1 structural analysis.

## Context
ADR-0006 left a **termination clause armed**: if a third enrichment attempt
failed to lift the top-3 ceiling above OFF's 63.3%, the accumulated evidence
(three negative results) would be the verdict — offline document-text
manipulation cannot reach the v1 target. Form C — *selective* enrichment that
injects a parent level **only when its text discriminates between siblings
rather than homogenizing them** — was that third attempt. Where ADR-0005 (FULL)
and ADR-0006 (B) assumed which level to inject and lost, C proposed to *measure*
genericity directly and inject only the discriminating remainder.

The CP1 charge was deliberately gated: investigate whether C is implementable
**without overfitting** (a binary, structural discriminator with no eval-tuned
numeric parameter) and what its **ceiling** is — *before* writing any code or
running any eval. With the termination clause in force and the discriminator
carrying the most degrees of freedom of the whole series, the bar was: C is only
honest if the rule is binary and structural; if it needs a tunable threshold, it
collapses into a count/length rule (Form A) and is not worth implementing.

## Investigation (not implementation)
CP1 measured verbatim text sharing across the 34 Chapter 22 NCMs and evaluated
candidate discriminators against the seven distinct substantive subheadings.

- **Heading level: C ≡ B.** By construction the 4-digit `heading_description` is
  identical across all children of a heading, so under "inject only if unique
  among siblings" the heading is **never** injected (the two single-child
  headings, 22.03 / 22.09, carry an empty description anyway). C inherits B's
  conscious sacrifice of the narrow product-naming headings (Vermutes 22.05,
  fermented beverages 22.06) — both have an empty subheading, so C enriches
  *nothing* there.

- **Sharing alone does not separate product from refinement.** The case the
  user flagged holds: `"Uísques"` (2208.30, shared verbatim across its three
  leaves) and `"Outros vinhos; mostos…"` (2204.21/29, shared across sibling
  subheadings) are *both* shared. Neither definition of "sibling sharing"
  (across leaves of one subheading, or across subheadings of one heading)
  distinguishes the short product name we want to keep from the long legal
  refinement we want to drop. A second axis is required.

- **A binary, structural discriminator does exist.** The OR of two
  parameter-free predicates classifies all seven *clean* substantive subheadings
  correctly — keep `{Vinhos espumantes…, Uísques}`, drop
  `{Outros vinhos…×3, Álcool etílico…×2}`:
  - **P1 — legal markers**: text starting with `"Outros"`, or containing `";"`,
    `"cuja"`, `"exceto"` — HS/TIPI drafting conventions for residual and
    restrictive clauses, not product names. (Catches the wines; misses the
    ethanols.)
  - **P2 — redundant with heading**: the subheading is an exact
    (case-insensitive) substring of its own `heading_description`, so it restates
    the family text and carries no signal beyond the heading we already never
    inject. (Catches the ethanols; misses the wines.)

  Neither predicate has a tunable numeric parameter, so C **clears the
  anti-overfitting bar** and does not collapse into Form A — the length signal
  that *tried* to separate `"Uísques"` (7 chars) and `"Vinhos espumantes…"`
  (37 chars) from `"Álcool etílico não desnaturado…"` (85 chars) was deliberately
  not used.

- **Ceiling: a 5-of-34 perturbation of OFF.** Under the minimal rule C injects a
  subheading on only **five leaves** — espumantes (2204.10.10/.90) and Uísques
  (2208.30.10/.20/.90). Everything else equals OFF. C removes exactly B's
  regressors (the wine/ethanol subheadings, cases 016/017/024 → back to OFF
  ranks) while keeping B's one recovery (015, espumantes). Optimistic ceiling:
  recover one or two cases; top-3 near or slightly above 63.3%. C structurally
  **cannot** help the majority of Chapter 22, whose subheadings are empty (vodca,
  gim, licores, vinagre, Vermutes, Sidra).

- **The high-value case already failed.** Uísques/case-026 (Johnnie Walker) was
  C's best hope, and it dropped to rank 8 under B; under C its outcome was, at
  best, *uncertain* — a colloquial-gap case ("Johnnie Walker" never matches
  "Uísques") that injecting the subheading does not address.

- **Honest leak.** Two ethanol subheadings (2207.20.11/.19) carry a parser-
  appended fragment (`". Álcool etílico"`) that breaks P2's exact-substring test
  and lacks P1's markers, so C would misclassify and inject them. Catching them
  would require clause-splitting normalization — a new degree of freedom
  justified by a *parser artifact*, not TIPI structure, and the first step toward
  Form A. The minimal honest rule leaves the leak in place.

## Decision
**Do not implement C.** The information value of measuring is low: the structural
analysis is already decisive. The discriminator that clears the overfitting bar
touches only 5 of 34 leaves, its single highest-value case already failed under
B, and its optimistic ceiling is a *tie* with OFF. Spending a session to index,
measure, and very probably confirm `top-3 ≈ 63.3%` adds cost without changing the
verdict. The termination clause fires on the structural evidence.

## Root finding (consolidates ADRs 0005–0007)
Three enrichment experiments — FULL (53.3%), B (53.3%), C (not worth measuring) —
converge on one conclusion: **the bottleneck is not missing document context; it
is the discriminative power of e5-small between siblings.** Enrichment treats on
the surface (document text) a problem whose root is embedding quality. The
structure of Chapter 22 makes this concrete: most NCMs have an **empty
subheading** (vodca, gim, licores, vinagre, Vermutes, Sidra) — there is no useful
parent level to inject, so no amount of selective text manipulation reaches them.
Offline text manipulation does not get this corpus to the 70% top-3 target; the
next lever must improve the embedding itself, not the text fed to it.

## Consequences
- **Enrichment line closed.** `OFF` (33.3% / 63.3%) remains the baseline and what
  ships. FULL and B stay behind the flag, reproducible (`make eval-full`,
  `make eval-subheading`); C was never implemented.
- **The `EnrichStrategy` enum is unchanged** (`OFF` / `FULL` / `SUBHEADING_ONLY`).
  No new value is added — there is no `SELECTIVE` strategy, by design.
- No new analysis snapshot (C was not measured). The B/FULL data underpinning the
  root finding remain at `docs/adr/assets/0006-analysis.json`.

## Path Forward — retrieval quality, in order of increasing cost
The project's cost discipline (defer cost to the last possible point) orders the
candidates by recurring cost, not by expected accuracy:

1. **ADR-0008 (recommended) — swap the embedder for bge-m3** (`BAAI/bge-m3`,
   deferred in ADR-0004 to avoid adding a second variable). Offline, **zero
   recurring cost**, strong multilingual coverage in Portuguese, trained for
   retrieval. Attacks the root (discriminative power) instead of the surface.
   Measure the delta against the OFF e5-small baseline (63.3%).
2. **Gemini `text-embedding-004`** — a **one-time** indexing cost (cents for 34
   docs) and a fraction of a cent per query for one embedding call, **not** a
   full LLM call. The candidate if offline bge-m3 is not enough.
3. **LLM rerank** — a **recurring per-query** cost (a full LLM call every time).
   The most expensive option and the one most likely to cross the target, but it
   pushes against the CLAUDE.md budget (R$ 0.10 / 4 s). It is the **last** resort
   on cost, not the next step.
4. **Recalibrate the v1 target** if no acceptable cost crosses 70%.

Recorded explicitly: **rerank is the last point by cost, not the next one.**
Swapping the embedder (zero or one-time cost) precedes reranking (recurring cost)
by the project's cost principle — the same principle that kept LLM rerank deferred
through ADRs 0005–0006.

## References
- Predecessors: `docs/adr/0004-semantic-retrieval-e5-small.md` (e5-small chosen,
  bge-m3 deferred), `docs/adr/0005-hierarchical-enrichment.md` (FULL),
  `docs/adr/0006-subheading-only-enrichment.md` (B).
- Data underpinning the root finding: `docs/adr/assets/0006-analysis.json`
  (per-case B/FULL scores, ranks, ECE bins).
- TIPI source for the CP1 structural analysis: `data/tipi/tipi_22_20260612.json`.
