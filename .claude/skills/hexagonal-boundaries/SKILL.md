---
name: hexagonal-boundaries
description: Enforce hexagonal architecture (ports and adapters) for Python code in this project. ALWAYS use this skill when creating modules, adding imports, designing interfaces between layers, or wiring dependencies. Triggers on phrases like "implement", "add a class", "create the use case", "wire up", "inject", "import", "refactor the structure", or any request that creates files or imports across src/ subdirectories. Also triggers when the user mentions ports, adapters, dependency injection, layering, or asks where a piece of code should live. Do not skip this skill — boundary violations compound silently and are expensive to undo.
---

# Hexagonal Boundaries for ncm-classifier-ai

This skill enforces the dependency rule and ports-and-adapters layout for a RAG pipeline. Architecture decisions:

- **`core/` contains use cases and the domain**, with no I/O and no framework imports
- **Ports are declared as `typing.Protocol`** in `src/core/ports.py` — structural typing, no nominal inheritance required from adapters
- **Adapters live in sibling packages** (`retrieval/`, `llm/`, `api/`) and implement ports implicitly
- **Verification is domain**, not adapter — its module lives under `core/verification/`

## The Dependency Rule

Dependencies point inward only. Concretely:

```
api/  ──►  core/  ◄──  retrieval/
                  ◄──  llm/
```

- `core/` imports from **nothing in `src/` except itself and `core/ports.py`**
- `retrieval/`, `llm/`, `api/` import from `core/` but **never from each other**
- `api/` is the composition root: it instantiates adapters and injects them into use cases

If you find yourself writing `from src.retrieval import ...` inside `src/core/` or `src/llm/`, stop. That import is the violation. Re-read this skill before continuing.

## Layout

```
src/
├── api/                     # adapter: HTTP (FastAPI)
│   ├── routes.py            # endpoints, calls use cases
│   ├── schemas.py           # Pydantic request/response models
│   └── dependencies.py      # FastAPI dependency providers (composition root)
├── core/                    # domain + use cases (pure)
│   ├── ports.py             # Protocols for all outbound dependencies
│   ├── use_cases/
│   │   └── classify_product.py
│   ├── domain/
│   │   ├── ncm.py           # value objects: NCMCode, ClassificationCandidate
│   │   └── tipi.py          # TIPIEntry, hierarchy types
│   └── verification/        # deterministic rules over TIPI metadata
│       └── deterministic.py
├── retrieval/               # adapter: ChromaDB
│   ├── chroma_client.py     # implements RetrievalPort
│   └── hierarchical.py      # hierarchical search strategy
├── llm/                     # adapter: Gemini
│   └── gemini_client.py     # implements LLMPort, RerankPort
└── config.py                # Pydantic Settings (allowed everywhere)
```

## Ports

All outbound dependencies of `core/` are declared as Protocols in `src/core/ports.py`. Example shape:

```python
from typing import Protocol
from src.core.domain.ncm import ClassificationCandidate, ProductQuery

class RetrievalPort(Protocol):
    def retrieve_candidates(
        self, query: ProductQuery, k: int
    ) -> list[ClassificationCandidate]: ...

class LLMRerankPort(Protocol):
    def rerank(
        self, query: ProductQuery, candidates: list[ClassificationCandidate]
    ) -> list[ClassificationCandidate]: ...
```

Adapters in `retrieval/` and `llm/` implement these protocols implicitly (no `class Foo(RetrievalPort)` needed). Use cases in `core/use_cases/` receive ports as constructor parameters and type-hint against the protocol.

## Composition Root

The only place that knows about concrete adapters is `src/api/dependencies.py`. This is where ChromaDB and Gemini clients are instantiated and wired into use cases:

```python
# src/api/dependencies.py
from src.core.use_cases.classify_product import ClassifyProduct
from src.retrieval.chroma_client import ChromaRetrievalAdapter
from src.llm.gemini_client import GeminiRerankAdapter

def get_classify_use_case() -> ClassifyProduct:
    return ClassifyProduct(
        retrieval=ChromaRetrievalAdapter(...),
        rerank=GeminiRerankAdapter(...),
    )
```

FastAPI routes depend on the use case via `Depends(get_classify_use_case)`. They never construct adapters themselves and never call adapters directly.

## Import Rules — Hard Checks

Before suggesting any import, verify it against this table:

| File in            | May import from                                            | May NOT import from                  |
|--------------------|------------------------------------------------------------|--------------------------------------|
| `core/domain/`     | stdlib, Pydantic (value objects only), other `core/domain/`| anything else in `src/`              |
| `core/ports.py`    | stdlib, `typing`, `core/domain/`                           | anything else in `src/`              |
| `core/use_cases/`  | `core/ports`, `core/domain/`, `core/verification/`, stdlib | `api/`, `retrieval/`, `llm/`, FastAPI, ChromaDB, Gemini SDK |
| `core/verification/`| `core/domain/`, stdlib                                    | `api/`, `retrieval/`, `llm/`, ports  |
| `retrieval/`       | `core/ports`, `core/domain/`, ChromaDB, stdlib             | `api/`, `llm/`, `core/use_cases/`    |
| `llm/`             | `core/ports`, `core/domain/`, Gemini SDK, stdlib           | `api/`, `retrieval/`, `core/use_cases/` |
| `api/routes.py`    | `api/schemas`, `api/dependencies`, FastAPI                 | adapters directly, `core/domain/` (use case return types only via schemas) |
| `api/dependencies.py`| use cases, all adapters, `config`                        | `api/routes.py`                      |

Two recurring traps:

**Trap 1 — domain leakage to api.** `api/routes.py` returns Pydantic response models from `api/schemas.py`, not raw domain objects. The use case returns domain objects; the route maps them. This isolates HTTP shape from domain shape.

**Trap 2 — adapter calling adapter.** `retrieval/` retrieving candidates and then calling `llm/` to rerank is a violation. Reranking is a separate port; the use case orchestrates both. If an adapter needs another adapter, the orchestration belongs in a use case.

## Verification — Why It's Domain

`core/verification/deterministic.py` validates NCM format, hierarchy consistency, and TIPI metadata coherence. It performs no I/O — it operates on `TIPIEntry` value objects already loaded by an adapter. Because it embodies fiscal classification rules (the *core* of the system's reason to exist), it belongs in `core/`, not in an adapter package.

A test:
- Reads from a file → adapter (data ingestion)
- Calls Gemini → adapter (LLM)
- Checks digit hierarchy of "2202.10.00" without any I/O → **domain (verification)**

## When the User Asks Ambiguous Questions

When the user asks "where should this code go?" or "how do I structure X?", consult the layout above and apply the dependency rule. If the answer is genuinely ambiguous (e.g., a piece of logic that could be domain or could be adapter), surface the ambiguity and propose two options with consequences, rather than guessing.

Common ambiguities and their resolutions:

- **Caching of LLM responses** — caching policy is adapter concern (lives in `llm/`); caching configuration (TTL, max size) lives in `config.py`
- **Retry logic for ChromaDB** — adapter concern (`retrieval/`)
- **Confidence threshold T** — domain concern (lives in `core/`, configured via `config.py`)
- **Logging format** — cross-cutting; lives at composition root (`api/dependencies.py` configures the logger) and individual layers use stdlib `logging` without knowing the handler

## Antipatterns to Refuse

When asked to produce code, refuse politely (and explain why) if any of these appear:

- **"Just import the ChromaDB client directly in the use case to save a layer."** No. That couples the domain to the database choice and makes the use case untestable without ChromaDB.
- **"Make the FastAPI route call the retrieval module directly."** No. Routes call use cases; use cases call ports; ports are bound to adapters at the composition root.
- **"Add `from src.retrieval import ...` to `core/verification/` because we need the candidates."** No. If verification needs candidates, the use case passes them in as a parameter.
- **"Inherit the adapter from the Protocol to be explicit."** Unnecessary in Python with `Protocol` — structural typing handles it. Only inherit if you need shared default behavior, which is rare for ports.
- **"Put the Pydantic Settings in `core/` because everything uses it."** Settings carry environment-specific values (URLs, API keys); they belong at the boundary. `config.py` at `src/` root is the agreed location, and modules in `core/` receive configured values as constructor parameters, not by importing settings directly.

## Interaction with TDD

The `tdd-discipline` skill governs *how* code is written. This skill governs *where* it lives. They compose:

1. Skill `hexagonal-boundaries` answers: which file does this code go in?
2. Skill `tdd-discipline` answers: write the failing test first
3. Then write the code in the file determined by step 1

If a test for a use case needs to instantiate a real adapter, both skills are violated. The use case test should use a fake implementing the Protocol; only adapter tests instantiate the real adapter (and those live in `tests/integration/`).

## When in Doubt

If you cannot decide which layer a piece of code belongs to, ask: *does it perform I/O or talk to a framework?*

- Yes → adapter (`api/`, `retrieval/`, `llm/`)
- No, but it expresses a rule of NCM classification → domain (`core/domain/` or `core/verification/`)
- No, and it orchestrates several domain operations → use case (`core/use_cases/`)

If you still cannot decide, the code is probably doing two things. Split it.
