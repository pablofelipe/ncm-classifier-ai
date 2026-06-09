# NCM Classifier — Problem Definition

## Problem

Brazilian companies that sell physical goods need to assign an 8-digit NCM
(Nomenclatura Comum do Mercosul) code to every product in their catalog.
The code determines IPI rates, ICMS rules, import/export taxes, and is
required on every NF-e (electronic invoice).

Misclassification is expensive:

- Fines from Receita Federal for incorrect fiscal treatment
- Blocked shipments at customs for export operations
- Retroactive tax assessments during audits (5-year window)
- Wrong tax burden — companies overpaying or underpaying for years

Today, classification is done by:

1. **In-house fiscal analysts** — slow, expensive, inconsistent across analysts
2. **Specialized consultants** — R$ 50–200 per SKU; doesn't scale for
   catalogs with thousands of items
3. **Rule-based software** (Sankhya, e-Auditoria, others) — brittle,
   requires manual keyword maintenance, weak on new product types

There is room for a system that classifies with high precision, exposes
confidence, and escalates uncertain cases to a human reviewer.

## Why a pure LLM does not solve this

A general-purpose LLM (GPT-4, Gemini, Claude) fails at this task because:

- It does not have the full TIPI table memorized; when asked for an NCM
  code it frequently hallucinates plausible-looking 8-digit numbers
- Even when it recalls a code, it cannot reliably distinguish between
  visually similar codes that differ in material, function, or use
- It has no audit trail — required for regulated environments
- It cannot express calibrated confidence — required for human-in-the-loop

Solution: a RAG pipeline grounded on the official TIPI table, with
structured retrieval (hierarchical: section → chapter → heading → NCM),
explicit verification step, and confidence-gated escalation.

## Users and buyers

| Role | Pain | Willingness to pay |
|------|------|---------------------|
| E-commerce ops manager | Catalog onboarding bottleneck | High (per-SKU cost today) |
| Fiscal analyst | Tedious, repetitive classification | Medium |
| Tax consultant | Wants leverage to handle more clients | High |
| Compliance officer | Wants auditable, defensible classifications | High |

This project does not need to acquire users to be valuable as a portfolio
piece — but framing decisions around real users keeps the design honest.

## Scope — v1 (4 weeks)

**In scope:**

- Classify products from a **single NCM chapter** (to be picked — see below)
- Input: product name + short description (≤ 300 characters)
- Output: top-3 NCM candidates with confidence scores + rationale citing
  the official TIPI entries used
- Retrieval grounded on the public TIPI table for that chapter
- Confidence gate: above threshold T → confident classification;
  below T → escalate (return ranked candidates, no single answer)
- Evaluation set with 30 labeled products, automated metrics
- Deployable on Fly.io or Railway (not localhost-only)
- README with metrics, cost-per-classification, architecture diagram

**Chapter selection criteria** (pick one before week 1 ends):

- 30–150 NCM codes total (bounded, but not trivial)
- Common in real catalogs (not obscure)
- Public product examples easy to source
- Candidates: Capítulo 33 (cosméticos), Capítulo 64 (calçados),
  Capítulo 95 (brinquedos), Capítulo 39 (plásticos — too broad?)

## Out of scope — v1

Explicitly NOT building in v1:

- Full TIPI coverage (all 96 chapters)
- Image-based classification (text only)
- Integration with ERP / NF-e systems
- Batch processing of large catalogs
- Multi-tenant / auth / UI beyond a basic API
- Reasoning across composite products ("kit" with mixed NCM)
- IPI/ICMS rate lookup (classification is enough for v1)

These are good v2/v3 candidates but each multiplies scope.

## Success criteria — v1

| Metric | Target | Stretch |
|--------|--------|---------|
| Top-1 accuracy on eval set | ≥ 70% | ≥ 85% |
| Top-3 accuracy on eval set | ≥ 90% | ≥ 95% |
| Confidence calibration (ECE) | ≤ 0.15 | ≤ 0.08 |
| Median latency per classification | ≤ 4s | ≤ 2s |
| Cost per classification | ≤ R$ 0.10 | ≤ R$ 0.03 |
| Deployable demo accessible via URL | Yes | — |

These numbers will be measured and published in the README. If targets
are not met, the README says so honestly — that is more credible than
fake numbers.

## Evaluation approach

Evaluation is built **before** the system. Concretely:

1. `eval/v1_cases.json` — 30 products with known correct NCM codes,
   sourced from public NF-e data (SEFAZ portals publish anonymized
   samples) and verified manually against the TIPI table
2. `eval/run_eval.py` — runs the classifier over all cases, computes
   top-1, top-3, and ECE
3. CI runs the eval on every push and publishes the numbers in the
   README via a badge or table
4. Every architectural decision (embedding model, chunking, re-ranking,
   prompt) is justified by a before/after eval delta, committed in
   `docs/adr/`

Without this, the project is a tutorial.

## Constraints

- Python 3.13, FastAPI, ChromaDB (persistent), Pydantic
- LLM: Google Gemini (Flash for retrieval-side, Pro for verification
  if needed). Configurable so the architecture is not vendor-locked.
- No LangChain, no LlamaIndex, no LangGraph. Direct SDK calls. If a
  library would save more than 200 lines of code, reconsider — but
  default is no.
- All decisions documented in `docs/adr/NNNN-title.md`

## Non-goals

- Becoming a product. This is portfolio-grade engineering, not a startup.
- Reaching state-of-the-art numbers. A well-engineered 75% is more
  valuable here than a fragile 90%.
- Demonstrating breadth of frameworks. The project demonstrates depth
  of reasoning under constraints.

## Open questions to resolve in week 1

1. Which chapter is picked? (decision recorded in ADR-0001)
2. Where does the labeled eval data come from? (public NF-e, manual
   labeling, or both?)
3. What is the confidence-gate threshold T? (set after first
   calibration measurement, not arbitrarily)
4. Will the verification step use a second LLM call, or a deterministic
   check against TIPI metadata?

These stay open. The README will not pretend they were obvious from
day one.