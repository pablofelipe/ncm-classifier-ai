---
name: tdd-discipline
description: Enforce strict Test-Driven Development discipline (Red-Green-Refactor) for Python code in this project. ALWAYS use this skill when writing, modifying, or extending any production code in src/, especially retrieval logic, verification rules, API endpoints, or LLM client wrappers. Triggers on phrases like "implement", "add a function", "create the module", "fix this bug", "refactor", or any request that produces or changes code under src/. Also triggers when the user asks to "write tests for X" or mentions pytest, fixtures, mocks, or coverage. Do not skip this skill for "small" changes — TDD discipline is non-negotiable in this codebase.
---

# TDD Discipline for ncm-classifier-ai

## Domain Glossary

Brazilian fiscal terms used throughout this project:

- **NCM** (*Nomenclatura Comum do Mercosul*) — the 8-digit code that classifies a product for tax and customs purposes across Mercosur countries; the value this pipeline predicts.
- **TIPI** (*Tabela de Incidência do Imposto sobre Produtos Industrializados*) — the official Brazilian table mapping each NCM code to its IPI tax rate; the authoritative source this system retrieves from.
- **ex-tarifário** — a temporary exception entry nested under an NCM code that grants a reduced tax rate to a specific product variant. Kept in pt-BR: it is Brazilian fiscal jargon with no direct technical translation.

This skill enforces strict Test-Driven Development for a RAG pipeline classifying products into Brazilian NCM codes. The project is eval-first (see `CLAUDE.md`), and TDD is the unit-level counterpart to that discipline: nothing ships without a failing test that motivated it.

## The Hard Rule

**Production code is written only to make a failing test pass.** Never the other way around. If you find yourself writing code in `src/` before a test exists in `tests/`, stop and write the test first.

This rule has exactly three exceptions, all narrow:

1. **Pure scaffolding** — empty `__init__.py`, type stubs, Pydantic schemas that hold no logic. Schemas are tested indirectly through the functions that use them.
2. **Throwaway exploratory scripts** in `scripts/` clearly marked as such, never imported by `src/`.
3. **TIPI data ingestion one-shots** in `scripts/ingest_tipi.py` where the validation is the produced JSON itself (verified manually against the source PDF).

Every other line in `src/` follows Red-Green-Refactor.

## The Cycle

### Red — write a failing test

Before touching `src/`, write a test in `tests/` that expresses the behavior you want. The test must fail for the right reason (assertion fails, not import errors). Run it once and confirm the failure message before proceeding:

```bash
pytest tests/path/to/test_x.py::test_specific_behavior -v
```

Three checks before moving to Green:
- The test fails with an assertion error or an explicit `pytest.fail()`, not with `ImportError` or `AttributeError` from missing scaffolding
- The test name reads as a behavior statement (`test_returns_empty_list_when_no_candidates_match`, not `test_retrieve`)
- The assertion is on observable behavior, not on internal state or implementation details

### Green — minimum code to pass

Write the smallest amount of production code that turns the test green. This often feels embarrassing — a hard-coded return value, a single `if` branch. That is correct. You are *not* writing the final implementation; you are establishing the contract.

Run the targeted test and confirm green. Then run the full test suite:

```bash
make test
```

If anything else broke, you violated isolation somewhere. Fix that before moving on.

### Refactor — clean up under green

Now improve the code while keeping the suite green. Acceptable refactors at this stage:
- Extract methods, rename for clarity, collapse duplication
- Replace the hard-coded return with the real algorithm
- Introduce abstractions (Protocol, ABC) only if a second test demands them — never speculatively

Run the full suite after every meaningful change. If it goes red, undo the last refactor and try smaller steps.

## Project-Specific Rules

### Layering and isolation

This project follows hexagonal boundaries declared in `CLAUDE.md`. Tests respect those boundaries:

- **`src/verification/` (domain)** — tested with pure unit tests, no I/O, no mocks needed
- **`src/retrieval/` (adapter for ChromaDB)** — tested with a fake ChromaDB client (fixture), not against a real database
- **`src/llm/` (adapter for Gemini)** — tested with a recorded-response fake, never hitting the live API in unit tests
- **`src/api/` (adapter for HTTP)** — tested with FastAPI's `TestClient`, mocking the use case layer
- **`src/core/` (use cases)** — tested with Protocol-based test doubles for retrieval and LLM ports

If a unit test needs network, environment variables for live credentials, or a real ChromaDB persistence file, it is not a unit test. Move it to `tests/integration/` and exclude from the default `make test`.

### Test types and folders

```
tests/
├── unit/           # Fast, isolated, no I/O. Run on every save.
├── integration/    # Real ChromaDB, real Gemini (with cassettes). Run on demand.
└── conftest.py     # Shared fixtures (fake_chroma, fake_gemini, sample_tipi_entry)
```

Default `make test` runs only `tests/unit/`. CI runs both.

### Fixtures over setup

Prefer pytest fixtures over `setUp`-style class methods. Compose small fixtures:

```python
@pytest.fixture
def sample_tipi_entry():
    return TIPIEntry(ncm="2202.10.00", section="IV", chapter="22", ...)

@pytest.fixture
def fake_chroma(sample_tipi_entry):
    client = FakeChromaClient()
    client.upsert([sample_tipi_entry])
    return client
```

### Assertion style

One logical assertion per test. If you need multiple `assert` statements, they must all express the same behavior (e.g., asserting structure of a returned object).

Bad — three different behaviors in one test:
```python
def test_classify():
    result = classify("Coca-Cola 350ml")
    assert result.top_ncm == "2202.10.00"
    assert result.confidence > 0.7
    assert len(result.candidates) == 3
```

Good — split into three tests with descriptive names:
```python
def test_returns_expected_ncm_for_well_known_product(): ...
def test_high_confidence_for_unambiguous_product(): ...
def test_always_returns_three_candidates(): ...
```

### Pydantic v2 models

Schemas in `src/api/schemas.py` and similar are not tested directly. They are exercised through the functions that consume them. Only test custom validators (`@field_validator`, `@model_validator`) and only when they implement non-trivial logic (NCM format regex, length bounds, mutually exclusive fields).

### Parametrize ruthlessly

For NCM format validation, retrieval ranking, confidence calibration — anything that has a table of input/expected pairs — use `@pytest.mark.parametrize`. The eval set in `eval/v1_cases.json` is *not* the unit test suite, but parametrized unit tests on edge cases (empty description, max-length input, special characters, NCM with `ex-tarifário`) are.

## Antipatterns to Refuse

When the user asks you to produce code, refuse politely (and explain why) if any of these appear:

- **"Write the function and then we'll add tests later."** No. Write the test first.
- **"Just mock everything so the test passes."** A test that mocks the thing it's testing is theater. Mock the *collaborators*, not the system under test.
- **"Skip the test, it's a small change."** Small changes are where regressions hide. Especially in retrieval scoring or confidence math.
- **"This test is slow, let me cache the LLM response in the test itself."** Move it to `tests/integration/` with a recorded cassette, not inline.
- **"Increase coverage to X%."** Coverage is a lagging indicator. Pursue behaviors worth testing, not a percentage. If asked for coverage as a goal, push back and ask which behaviors are currently untested.

## Interaction with Eval-First Discipline

The project's `CLAUDE.md` requires `eval/v1_cases.json` and `eval/run_eval.py` to gate architectural changes. TDD operates at a finer grain:

- **Eval suite** validates end-to-end behavior of the classifier (top-1, top-3, ECE)
- **Unit tests** validate components in isolation (does the verification reject a malformed NCM, does the hierarchical retrieval return results in the right order)

A change to embedding model, chunking strategy, or re-ranking touches both: unit tests for the new component logic, plus a before/after eval delta in `docs/adr/`. Neither replaces the other.

## When in Doubt

If you cannot decide whether to write a test for a given change, the answer is yes. The cost of a redundant test is minutes. The cost of an undetected regression in fiscal classification is a customer audit.

If you cannot figure out *how* to test a piece of code, that is a design signal. The code is probably doing too much, or has a hidden dependency that should be a constructor parameter (Protocol). Refactor for testability before writing the test, then write the test, then write the code.
