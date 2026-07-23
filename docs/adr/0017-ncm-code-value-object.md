# ADR-0017 — `NCMCode` Value Object

**Status:** Accepted — ships
**Date:** 2026-07-23
**Deciders:** Pablo Felipe

---

## Context

`docs/architecture-review-2026-07.md` (Section 3) flagged the domain as modeled mostly with anemic dataclasses, and specifically called out `ClassificationCandidate.ncm_code: str` and `TIPIIndex`'s dict keys as primitive obsession: "is this a valid NCM code" and "what's its hierarchy" were resolved by regexes and string operations scattered across `tipi_parsing.py` and `deterministic.py`, with no single source of truth. That review deliberately deferred the fix to a dedicated ADR rather than bundling it into a lint-hygiene pass.

A deeper audit (three parallel searches over every producer/consumer of an NCM code string, plus direct reading of the LLM rerank and hybrid-fusion call sites) confirmed the actual shape of the problem:

- The canonical format in live use is always **dotted** (`"2202.10.00"`) — `ClassificationCandidate.ncm_code`, `TIPIEntry.ncm`/`heading`/`subheading`, `data/tipi/*.json`, `eval/*_cases.json`, and the HTTP response schema all agree on it.
- **Dotless** (`"22021000"`) exists only as infrastructure: ChromaDB document `id`s, and the internal keys of `TIPIIndex._codes`. Three call sites did the dotted→dotless conversion by hand with `.replace(".", "")`: `chroma_client.py`, `api/dependencies.py`, and `classify_product.py`.
- `HybridRetrievalAdapter` (ADR-0011) fuses candidates from two retrievers using a plain `dict[str, float]` keyed by `candidate.ncm_code`. This works today only because every adapter happens to agree on the dotted format by convention — nothing enforces it. A future adapter returning a differently-formatted code would silently fail to fuse, with no error.
- `NCMCandidate.ncm` (the HTTP response field) had **no format validation at all** — unlike `EvalCase.expected_ncm`, which already carried a `pattern` constraint.

## Decision

Introduce `NCMCode` (`src/core/domain/ncm.py`) as a frozen `dataclass` Value Object:

```python
NCM_CODE_RE = re.compile(r"^\d{4}\.\d{2}\.\d{2}$")

@dataclass(frozen=True)
class NCMCode:
    value: str

    def __post_init__(self) -> None:
        if not NCM_CODE_RE.fullmatch(self.value):
            raise ValueError(...)

    def __str__(self) -> str:
        return self.value

    @property
    def dotless(self) -> str: ...

    def matches_heading(self, heading: str) -> bool: ...
```

`frozen=True` gives structural `__eq__`/`__hash__` for free, which is what makes it safe to use as a dict key (`HybridRetrievalAdapter`'s RRF fusion, `TIPIIndex`'s lookup). No `.chapter` or other property was added speculatively — only what an actual call site needed. `matches_heading()` absorbs `TIPIIndex._hierarchy_consistent`'s comparison logic (previously a free function normalizing both sides by hand); the redundant `len(code) != 8` guard disappears because construction already guarantees it.

**Wired into:** `ClassificationCandidate.ncm_code`, `TIPIIndex` (both its `codes` dict keys and `verify()`'s parameter), `VerificationResult.code`, the four retrieval adapters, `HybridRetrievalAdapter`'s fusion dict, `chroma_client.index_entries` (constructs one `NCMCode` per entry, uses `.dotless` for the Chroma `id`), `GenericLLMRerankAdapter` (defensive parsing — see Consequences), the HTTP boundary (`routes.py` converts back to `str` at the response edge; `NCMCandidate.ncm` gained `Field(pattern=NCM_CODE_RE.pattern)`), and `eval/run_eval.py`'s top-1/top-3 comparison.

**Deliberately NOT wired into** `TIPIEntry`/`tipi_parsing.py`/`scripts/ingest_tipi.py`: `TIPIEntry.ncm` is serialized via `dataclasses.asdict()` into `data/tipi/*.json`, a one-shot ingestion path (documented TDD exception), not the live classification pipeline. Changing its type would ripple into JSON serialization for no benefit to the actual request path. `tipi_parsing.py` was instead changed to import `NCM_CODE_RE` from `ncm.py` rather than keep its own duplicate `_NCM_FULL_RE` — same validation, no type change.

**No cross-type equality** (`NCMCode == str`): rejected deliberately. Allowing it would have shrunk the test diff, but it would also quietly defeat the point of a typed Value Object. `mypy --strict` (scoped to `src/`) was used as a checklist during the migration — every site the type change touched surfaced as a type error, which is the intended trade: a bigger diff today for a boundary that can't silently regress to string-typed comparisons tomorrow.

## Alternatives Considered

**Also type `TIPIEntry.ncm` as `NCMCode`.** Rejected: breaks `asdict()`-based JSON serialization used by `scripts/ingest_tipi.py` for no benefit — ingestion is a one-shot script, not the live path this ADR is improving.

**Allow `NCMCode == str` comparisons.** Rejected: weakens the type-safety this ADR exists to add. `mypy strict` already turns the "extra churn" into a mechanical, low-risk checklist rather than a real cost.

**Skip the API-schema validation, since it's outside the value-object refactor's original scope.** Rejected: the gap was concrete and already documented in the review (`NCMCandidate.ncm` had zero format validation), the fix is one `Field(pattern=...)` line reusing the existing pattern, and leaving it unvalidated after introducing a validating domain type one layer down would have been an inconsistent half-measure.

## Measured Delta

This is a pure refactor — no retrieval, rerank, or scoring logic changed. The expectation was **identical** eval numbers before and after, confirmed on both corpora after rebuilding each index from scratch against the new indexing code path:

| Config | Top-1 | Top-3 |
|---|---|---|
| v1 (30 cases, Ch.22, dense/passthrough — CI baseline) | 33.3% (10/30) | 63.3% (19/30) |
| v2 (350 cases, Ch.20/21/22, hybrid/passthrough) | 49.1% (172/350) | 68.0% (238/350) |

Both match their respective historical baselines (ADR-0004 for v1, ADR-0011 for v2) exactly. The v2 run additionally exercises `TIPIIndex.verify`/`NCMCode.matches_heading` across three chapters, not just one — the hierarchy-consistency path this ADR touched most directly.

v2 was run with `RETRIEVAL_MODE=hybrid` only (no LLM rerank) to keep the check at zero API cost, consistent with the standing rule against calling the Gemini API without explicit confirmation.

## Consequences

- **Closes the `HybridRetrievalAdapter` fusion risk**: the RRF dict is now keyed by a hashable, validated type instead of an unenforced string convention.
- **Closes the API validation gap**: `NCMCandidate.ncm` now rejects malformed codes at the HTTP boundary, matching `EvalCase.expected_ncm`'s existing contract.
- **Removes three manual `.replace(".", "")` conversions** (`chroma_client.py`, `api/dependencies.py`, `classify_product.py`), replaced by `NCMCode(...)` construction and a `.dotless` property at the one place (Chroma `id`s) that still needs the dotless form.
- **Two real (non-cosmetic) bugs surfaced and fixed while wiring this through**, neither caught by `mypy` (its Pydantic-plugin type-checking has a blind spot for this project's model construction, confirmed by a manual probe) — only by running the full test suite and manually exercising Pydantic at each step:
  - `routes.py` was passing `NCMCode` directly into a Pydantic `str` field; Pydantic rejects that at runtime (`validation error`), which would have 500'd every real `/classify` response. The route/middleware/rate-limit tests didn't catch it because their fake use cases still returned plain-`str` candidates — those fakes now build real `NCMCode` candidates so this boundary is actually exercised.
  - `eval/run_eval.py` compared an `NCMCode` prediction against a plain-`str` expected value. That doesn't raise — `NCMCode.__eq__` against a non-`NCMCode` just returns `False` — it would have silently zeroed every top-1/top-3 hit. Both are fixed with an explicit `str(c.ncm_code)` at the comparison/serialization boundary.
- **Discovered, not fixed**: `GenericLLMRerankAdapter`'s prompt (`generic_llm_rerank_adapter.py`) asks the LLM to return `{"ranked": ["NNNNNNNN", ...]}` — an 8-digit dotless placeholder — while the candidates rendered earlier in the same prompt are dotted (`"2202.10.00"`). If a model followed the placeholder literally, the returned codes would never match `pool`'s dotted keys, silently falling through to unranked order. This predates this ADR and is orthogonal to it (a prompt-wording issue, not a type issue); fixing the wording is a rerank-behavior change that needs its own measured eval delta against a live LLM, which is out of scope here. What this ADR *does* add is defensive robustness on the failure path: `GenericLLMRerankAdapter` now parses each ranked code as `NCMCode`, logging and skipping any that don't match the format instead of raising out of `rerank()` — the same degrade-gracefully behavior an unmatched (but well-formed) code already had.
- **`NCMCode` as the next domain-modeling extension point**: `.matches_heading()` is intentionally minimal (no `.chapter`, no `.heading` derivation) — grown only when an actual call site demands it, not speculatively.
