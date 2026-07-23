# Architecture Review — July 2026

**Reviewer stance:** Principal Architect / Staff Engineer perspective, applied to the project's declared hexagonal architecture (`CLAUDE.md`) and to a new set of engineering premises: TDD as a hard requirement, DDD as an architectural lens, and English-only code/docs/commits.

**Update:** all four recommendations below were implemented in follow-up commits after this review was first written — the `import-linter` architecture contract, moving `LLMClient` into `core/ports.py`, `pytest-cov` for local visibility, and the `NCMCode` Value Object (ADR-0017). Each is marked **Implemented** inline where it was originally recommended.

## 1. Purpose & Method

This review audits the current state of the codebase against Clean/Hexagonal Architecture and Domain-Driven Design principles, and against the project's own TDD/CI discipline. It is not tied to a single feature change, so it is not filed as a numbered ADR (`docs/adr/` records binary decisions with a measured before/after; this document is a multi-topic audit).

Method: automated exploration of `src/`, `tests/`, `.github/workflows/`, and `docs/adr/`, followed by direct verification of every claim below (grep for import boundaries, running `ruff`/`mypy`/`pytest` locally, reading the cited files). Findings are split into **fixed this round** (Section 5) and **recommended, not implemented** (Sections 2–4, explicitly marked) — the latter are deferred by an explicit product decision to keep this pass small and reversible, not because they are unimportant.

## 2. Hexagonal Architecture

### Boundary integrity

`src/core/` is clean: no import of `fastapi`, `chromadb`, `google.genai`, `pydantic`, `sentence_transformers`, or of `src.api`/`src.retrieval`/`src.llm` appears anywhere under `src/core/`. Every adapter (`src/retrieval/*`, `src/llm/*`) imports from `src.core.domain`/`src.core.ports`, never the reverse. This is the correct dependency direction and it holds today without exception.

### Ports and adapters

| Port | Declared in | Adapters |
|---|---|---|
| `RetrievalPort` | `src/core/ports.py` | `NaiveRetrievalAdapter`, `ChromaRetrievalAdapter`, `BM25RetrievalAdapter`, `HybridRetrievalAdapter` (composes two `RetrievalPort`s) |
| `LLMRerankPort` | `src/core/ports.py` | `PassthroughRerankAdapter`, `CrossEncoderRerankAdapter` (rejected by ADR-0012, kept for reproducibility), `GenericLLMRerankAdapter` |
| `LLMClient` | `src/core/ports.py` (moved — see finding below) | `GeminiClient` (only implementation today) |

Both `core/ports.py` ports have multiple real, ADR-justified implementations — not speculative interfaces. `LLMClient` having a single implementer is a documented, deliberate choice (ADR-0016), not an oversight.

### Finding: `LLMClient` is a port declared outside the hexagon — **Implemented**

`LLMClient` (originally `src/llm/llm_client.py:15-23`) was structurally a port — a `Protocol` that `GenericLLMRerankAdapter` depends on — but lived in `src/llm/`, an adapter package, rather than in `src/core/ports.py` alongside `RetrievalPort`/`LLMRerankPort`. `core/` never referenced it directly (correctly — `ClassifyProduct` only knows `LLMRerankPort`), so this was not a boundary violation in the strict sense checked above, but it was an inconsistency in where the project drew its own port/adapter line.

- **Fix applied:** the `Protocol` definition now lives in `src/core/ports.py`; `src/llm/llm_client.py` keeps only `resolve_llm_client()` (the factory, correctly infrastructure), importing the port back from `core`. `src/llm/generic_llm_rerank_adapter.py` updated its import accordingly.
- **Verification:** pure move, no behavior change — full unit suite (350 tests) and the new `import-linter` contract both stayed green before and after.

### Composition root

`src/api/dependencies.py` is the single composition root, structured as pure factory functions (`build_classify_use_case`, `_build_verification_index`, `_resolve_rerank_override`) wrapped by thin FastAPI-specific functions (`get_classify_use_case`) that read headers and `Depends()`-inject. This split is what lets `eval/run_eval.py` reuse `build_classify_use_case()` directly, with no FastAPI in the loop — a good example of keeping the composition logic framework-agnostic even though the composition root itself necessarily sits in `src/api/`. Dependency injection throughout the project is manual (no DI container), which is appropriate at this scale.

## 3. Domain-Driven Design

### What exists today

The domain (`src/core/domain/`, `src/core/verification/`) is modeled mostly as plain dataclasses carrying data with little behavior — closer to a data-centric than an object-oriented domain model. Two real exceptions:

- `ClassificationResult` (`src/core/domain/ncm.py:45-60`) enforces its own invariants in `__post_init__`: exactly 3 candidates, `confidence_label` drawn from a closed set. This is a Value Object with real behavior, not just a data holder.
- `TIPIIndex` (`src/core/verification/deterministic.py:32-58`) is the closest thing to a Domain Service: it encapsulates an in-memory NCM index and exposes `verify()`, with hierarchy-consistency logic (`_hierarchy_consistent`, lines 61-69) that is genuine business logic, not a getter.

Everything else — `ProductQuery` (`ncm.py:7-10`), `ClassificationCandidate` (`ncm.py:13-18`), `TIPIEntry`/`RawRow` (`src/core/domain/tipi_parsing.py`) — is anemic by DDD's definition: data with no behavior, with the corresponding logic (`candidate_metadata_from_entry`, `ncm.py:21-42`; `parse_tipi_rows`, `tipi_parsing.py:58-138`) implemented as free functions rather than methods.

There are **no Aggregates** in the DDD sense — no root entity governing transactional consistency over a cluster of objects. `TIPIIndex` is better described as an in-memory read model/lookup than an aggregate: nothing here has multi-object write consistency to protect, which is expected for a system with no persistence beyond an immutable, build-time-baked Chroma index.

### `NCMCode` as a Value Object — **Implemented (ADR-0017)**

At the time of the original review, "is this a valid NCM code" and "what's its hierarchy" were handled by ad hoc regexes and string operations scattered across `tipi_parsing.py` and `deterministic.py` (see Section 5 for the duplicate this caused). This was deferred to its own ADR rather than folded into the lint-hygiene pass, given its cross-cutting surface.

`NCMCode` (`src/core/domain/ncm.py`) now exists: a frozen dataclass validating the dotted format at construction, exposing `.dotless` and `.matches_heading()` — deliberately minimal, no `.chapter`/`.heading` properties added speculatively (nothing demanded them). It is wired into `ClassificationCandidate.ncm_code`, `TIPIIndex` (keys + `verify()`), `VerificationResult.code`, `HybridRetrievalAdapter`'s RRF fusion dict, all four retrieval adapters, `chroma_client.index_entries`, `GenericLLMRerankAdapter` (with defensive parsing so a malformed LLM-returned code can't crash `rerank()`), and converted back to `str` at the HTTP and eval boundaries. `TIPIEntry`/`tipi_parsing.py` deliberately kept `str` (JSON-serialized ingestion, not the live path) but now imports `NCMCode`'s regex instead of duplicating it.

Two real bugs surfaced during the wiring, neither caught by `mypy` (its Pydantic-plugin checking has a blind spot for this project's model construction — confirmed by directly probing it): `routes.py` passed `NCMCode` into a Pydantic `str` field (a runtime `ValidationError` on every real response), and `eval/run_eval.py` compared `NCMCode` against `str` (silently zeroing every top-1/top-3 hit, no crash). Both are fixed. Full detail, alternatives considered, and the measured before/after (v1 33.3%/63.3%, v2 hybrid 49.1%/68.0% — both reproduced exactly) are in `docs/adr/0017-ncm-code-value-object.md`.

### Bounded context

The project has a single bounded context (NCM classification over the TIPI table); there is no second subdomain in play, so bounded-context boundaries are not a live concern today. Worth revisiting only if a second business capability (e.g. IPI/ICMS rate lookup, explicitly out of scope per `CLAUDE.md`) is ever added.

## 4. TDD & Test Strategy

### Strengths

350 unit tests (post Section 5 cleanup), consistently following a fakes-by-port pattern: `tests/unit/core/use_cases/test_classify_product.py` injects hand-rolled `FakeRetrieval`/`FakeRerank` implementing the `Protocol`s structurally, never a mock of a concrete library. `unittest.mock`/`MagicMock` does not appear anywhere in `tests/`. The four `monkeypatch` usages in the whole suite are all legitimate adapter-boundary doubles (env/settings, or `google.genai.Client` inside `test_gemini_client.py` — the one adapter whose job is to wrap that SDK). Test names read as behavior statements (`test_execute_with_verification_failing_top_candidate_forces_needs_review`), not implementation descriptions. This is a genuinely well-disciplined test suite for a hexagonal codebase — nothing to fix here.

### Gaps

- **No architecture tests — Implemented.** The hexagonal boundary (Section 2) was enforced by convention and by the `hexagonal-boundaries` skill only, not by an automated check. An `import-linter` "forbidden" contract now runs as part of `make lint` (and therefore CI): `src.core` must not import `src.api`/`src.retrieval`/`src.llm` or `fastapi`/`chromadb`/`google`/`sentence_transformers`. Verified to actually catch a violation (a temporary `import fastapi` added to `core/ports.py` broke the contract as expected, then reverted) before being committed.
- **No code coverage tooling — Implemented (visibility only, as recommended).** `pytest-cov` is now a dev dependency with a `make coverage` target (`pytest --cov=src --cov-report=term-missing`). Deliberately **not** wired into CI as a numeric gate, matching the original recommendation: coverage percentage is a lagging indicator, and the project's existing fakes-by-port TDD discipline already produces the outcome coverage-chasing tries to approximate. Current baseline, for reference: 95% statement coverage on `src/` (`738` statements, `35` missed, concentrated in `chroma_client.py`'s CLI/rebuild paths, which unit tests correctly leave to integration coverage).

## 5. CI/CD & Production Readiness — Fixed This Round

Three mechanical, low-risk fixes were applied as part of this review, each its own commit:

1. **Removed dead code and its duplicate regex.** `validate_ncm_format` and its backing `_NCM_FORMAT_RE` (`src/core/verification/deterministic.py`) had no caller outside their own dedicated test — `TIPIIndex.verify` works on the dotless NCM form, so this dotted-format check was orphaned once ADR-0014 dropped the chapter-coherence path that would have used it. Deleting it also collapsed the duplicated NCM-format regex: the pattern actually used in production is `_NCM_FULL_RE` in `src/core/domain/tipi_parsing.py:4`.
2. **Lint hygiene.** Fixed two real `ruff check` violations (an unused import, a line over the 100-char limit) and reformatted five test files that had drifted from the `ruff format` baseline.
3. **Closed a CI gate gap.** `make lint` (`ruff check src eval && ruff format --check src eval && mypy src`) has existed as a documented `Makefile` target since early on but was never a step in `.github/workflows/eval.yml` — only `make test`, `make index`, `pytest tests/integration`, and `make eval` ran on push. It now runs on every push/PR, verified locally to pass at its current scope before being added, so it does not turn CI red.

### Other production-readiness state (unchanged, informational)

Diagnostics (`/`, `/health`, `/version`, `/info`), rate limiting, provider-error handling, and the Docker/Fly.io deployment artifacts already exist and are out of scope for this review (covered by ADR-0015/0016 and `docs/operational-notes.md`). The public deployment's live status is an infrastructure/billing matter tracked separately in `docs/operational-notes.md`, not a code-readiness concern.

## 6. Governance

- **Language.** README, all 16 ADRs, `ROADMAP.md`, `STATUS.md`, and `docs/operational-notes.md` are already entirely in English — no violation found. The only Portuguese strings inside `src/` are legitimate domain content: the PT-BR fiscal prompt sent to Gemini (`src/llm/generic_llm_rerank_adapter.py`, required because the classifier reasons about Brazilian fiscal descriptions) and an example product name in a docstring (`src/retrieval/bm25_adapter.py`). Neither is a comment describing code behavior in Portuguese.
- **Commit history.** `git log` shows commits already written in English throughout the project's history.
- **Claude Code configuration files.** `CLAUDE.md` and the two files under `.claude/skills/` are tracked in the repository today. This is an existing, intentional state — not changed by this review.

## 7. Explicitly Deferred Patterns (not adopted — reasoning recorded so it isn't re-litigated)

Per the review brief's own instruction to never recommend a pattern just because it's well-known, the following were considered and rejected for this system as it stands:

- **CQRS.** The system has exactly one write path (rebuilding the Chroma index at build/index time, entirely offline) and one read path (`ClassifyProduct.execute`, synchronous, no complex query variation). There is no divergence between read and write models to justify splitting them — introducing CQRS here would add indirection with no corresponding flexibility gained.
- **Outbox pattern.** There is no messaging, no event publishing, and no distributed transaction anywhere in the system — `ClassifyProduct` calls two injected ports and returns a value. The Outbox pattern solves dual-write consistency between a database and a message broker; neither exists here.
- **Event-Driven Architecture.** The entire pipeline is a synchronous request/response HTTP call (retrieve → rerank → verify → respond). There is no use case that benefits from decoupling producers from consumers via events, and introducing one would add operational complexity (a broker, delivery guarantees) the project has no current need for.

These may become relevant if the system's shape changes materially (e.g. batch processing or multi-tenant write paths, both explicitly out of scope per `CLAUDE.md`) — not before.
