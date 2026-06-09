# ADR-0002 — Verification Step: Deterministic TIPI Metadata Check

**Status:** Accepted  
**Date:** 2026-06-08

## Context

After the RAG pipeline retrieves and ranks NCM candidates, a verification step is needed to catch structurally invalid outputs before they reach the caller. The pipeline can produce a candidate that looks plausible but:

- Does not exist in the current TIPI table (hallucinated or stale code)
- Has the wrong chapter prefix (retrieval ranked a code from an adjacent chapter)
- Has an inconsistent digit hierarchy (e.g., heading digits don't match the declared section)

Two approaches were considered:

**Option A — Second LLM call**: prompt Gemini Pro to verify that the candidate is correct and consistent.  
**Option B — Deterministic check**: parse the candidate NCM against the in-memory TIPI metadata and validate structural invariants.

## Decision

**Option B — Deterministic TIPI metadata check.**

Validations performed, in order:

1. **Existence**: the 8-digit code appears in the indexed TIPI table for the current chapter
2. **Chapter coherence**: digits 1–2 of the NCM match the expected chapter (22 for v1)
3. **Hierarchy consistency**: the 4-digit heading and 6-digit subheading derived from the candidate exist as valid nodes in the TIPI tree

## Rationale

1. **Deterministic = testable**: the check is a pure function over TIPI metadata. It can be unit-tested exhaustively against the full chapter, with zero LLM cost and no flakiness.

2. **Zero additional latency or cost**: a second Gemini Pro call adds ~1–2 s and ~R$ 0.01–0.03 per classification. At the target cost of ≤ R$ 0.10, a second call consumes 10–30 % of budget on a step that can be replaced by a dictionary lookup.

3. **Audit-friendliness**: a deterministic rejection ("code 2202.10.00 not found in TIPI v20240101") is more defensible in a regulated context than "the LLM said it was wrong."

4. **Sufficient for structural errors**: the cases a second LLM call catches but a metadata check misses are semantic errors (e.g., correct code, wrong product category). Those are handled upstream by retrieval quality and confidence calibration, not by a verification gate.

## Alternatives Considered

- **Second LLM call (Gemini Pro)**: more flexible — could catch semantic mismatches, not just structural ones. Rejected because: (a) it adds cost and latency on every call, (b) it is non-deterministic and therefore hard to test, (c) the structural invariants are the only properties that can be checked without re-doing retrieval.
- **Hybrid (deterministic + LLM on low-confidence)**: reasonable future direction but adds complexity without a proven eval delta. Deferred to v2 if calibration shows systematic semantic errors that the structural check misses.

## Consequences

- `src/verification.py` (or equivalent) is a pure function: `verify(candidate: str, tipi: TIPIIndex) -> VerificationResult`
- The TIPI index must be loaded at startup and kept in memory; re-index on `make index`
- Rejected candidates are not returned as confident classifications — they are demoted to the "escalate" bucket with a `VERIFICATION_FAILED` reason code
- If all top-3 candidates fail verification, the response is always an escalation (no confident answer)
- Adds a test fixture requirement: a minimal in-memory TIPI stub for unit tests, independent of the real ChromaDB instance
