# ADR-0014 — Verification Gate Wiring (Chapter-Coherence Check Dropped)

**Status:** Accepted
**Date:** 2026-07-13
**Deciders:** Pablo Felipe

---

## Context

ADR-0002 specified deterministic verification as a post-rerank gate, implemented and
unit-tested in `src/core/verification/deterministic.py`, but never called by
`ClassifyProduct`. It was the last "planned, not yet wired" item left in the project.

`TIPIIndex.verify(code, expected_chapter)` compared the candidate against a fixed
`expected_chapter` sourced from `settings.ncm_chapter`. The active v2 configuration
(ADR-0009+) sets `NCM_CHAPTER=beverage` — a corpus label spanning Ch.20/21/22, not a
2-digit chapter prefix. Wiring the check as originally specified would have produced
two problems:

1. **Format bug**: `"22021000".startswith("beverage")` is always `False` (or vacuously
   mismatched for any real code) — every candidate would fail chapter-coherence and
   escalate, masking the 71.7%/75.7% result measured in ADR-0013.
2. **Design bug**: even with the string fixed, a check against a single fixed expected
   chapter doesn't fit a corpus that spans three chapters. The product's chapter is
   part of what the classifier is trying to determine — it is not a known input to
   verification.

A second, smaller mismatch: `validate_ncm_format` expects dotted format
(`"2202.10.00"`), while `TIPIIndex.verify` / `_hierarchy_consistent` expect the
dotless form (`"22021000"`). Candidates coming out of the pipeline carry the dotted
form (`ncm_dotted` in `ClassificationCandidate.metadata`), so the conversion must be
explicit at the wiring point.

## Decision

**Drop the chapter-coherence check. Keep existence + hierarchy-consistency only.**

- `TIPIIndex.verify(code, expected_chapter)` → `verify(code)` — the `expected_chapter`
  parameter and `VerificationStatus.WRONG_CHAPTER` are removed from
  `src/core/verification/deterministic.py`.
- `ClassifyProduct` accepts an optional `verification: TIPIIndex | None` constructor
  parameter. When set, the top reranked candidate is verified after reranking, before
  the confidence gate: `verify(candidate.ncm_code.replace(".", ""))`.
- A failing verification forces `confidence_label = "needs_review"` regardless of the
  rerank score, and sets a new field, `ClassificationResult.escalation_reason`, to the
  failing `VerificationStatus` value. On a pass (or when `verification=None`, preserving
  prior behavior), `escalation_reason` stays `None`.
- `verification=None` is the default, so existing callers and tests that don't pass a
  `TIPIIndex` are unaffected.

## Alternatives Considered

- **Dynamic chapter allow-list**: replace the fixed `expected_chapter` string with a
  set of chapters actually covered by the loaded corpus (e.g. derived from
  `NCM_CHAPTER=beverage` → `{"20", "21", "22"}`), and reject codes outside that set.
  Rejected as redundant: the `TIPIIndex` is built from the same corpus JSON that
  defines those chapters, so any code outside the covered chapters already fails the
  **existence** check — a code not in `self._codes` returns `CODE_NOT_FOUND`. A
  separate chapter allow-list would duplicate that check without adding coverage.
- **Fix the string bug only** (`expected_chapter` becomes a set derived from
  settings, keeping the enum value): considered and folded into the allow-list
  alternative above; rejected for the same reason.

**Revisit trigger**: if the `TIPIIndex` is ever built from a broader corpus than what
is actually served by the active retrieval collection (e.g. a shared multi-chapter
index reused across deployments with different `NCM_CHAPTER` scopes), the existence
check alone stops being equivalent to a chapter check, and the dynamic allow-list
alternative should be reconsidered.

## Consequences

- `VerificationStatus.WRONG_CHAPTER` is removed — a breaking change to the enum, but
  it had no callers outside `deterministic.py` itself (confirmed via repo-wide grep
  before the change).
- `ClassifyProduct`'s verification step is opt-in via constructor injection; the
  composition root (`src/api/dependencies.py`) builds the `TIPIIndex` from the same
  TIPI JSON already loaded for indexing (reusing `_find_latest_tipi_json`) and passes
  it in. Eval scripts that construct `ClassifyProduct` directly get the same gate for
  free, or can omit it for A/B comparison against the un-gated pipeline.
- `escalation_reason` is additive on `ClassificationResult` and `ClassifyResponse` —
  existing consumers of both are unaffected by the new optional field.
- Verification never changes *which* candidates are returned, only the
  `confidence_label`/`escalation_reason` — the top-3 list is unchanged even when the
  top candidate fails verification. A future ADR could explore demoting a
  verification-failed top candidate below a passing lower-ranked one, but that is out
  of scope here.
