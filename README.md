# NCM Classifier AI

A RAG pipeline that classifies Brazilian products into 8-digit NCM
(Nomenclatura Comum do Mercosul) fiscal codes, grounded on the official
TIPI table.

This repository is a portfolio project built under one constraint:
**every architectural decision is measured, not assumed.** Each change
to the retrieval pipeline is reported as an ADR with a before/after eval
delta — including the changes that didn't work. The decision log below
is the most useful part of this repo.

## Status (Chapter 22 — Beverages, spirits and vinegar)

| Metric | Current | v1 target |
|---|---|---|
| Top-1 accuracy | 33.3% (10/30) | ≥ 70% |
| Top-3 accuracy | **63.3% (19/30)** | ≥ 90% |
| ECE | 0.54 (uncalibrated) | ≤ 0.15 |
| Median latency | within budget | ≤ 4s |
| Cost / classification | within budget | ≤ R$ 0.10 |

The system does not yet meet the v1 accuracy target. What it does
demonstrate is the **method**: a disciplined, eval-gated investigation
that isolated the actual bottleneck — three independent enrichment
strategies were tried, measured, and rejected on evidence, narrowing the
problem from "which text do we feed the model" to "the embedding model's
discriminative power between similar products." That finding (ADR-0007)
is the real deliverable so far, and it directly motivates the next step
(ADR-0008).

## Architecture

Hexagonal / ports-and-adapters. Retrieval and rerank are swappable
adapters behind `RetrievalPort` and `LLMRerankPort`, validated by two
implementations each (naive baseline + production adapter). A
**deterministic verification gate** checks every candidate against the
in-memory TIPI table (existence, chapter coherence, hierarchy
consistency) before it can be returned as a confident answer — chosen
over a second LLM call because it's testable, has zero marginal cost,
and produces an auditable rejection reason. Candidates that fail
verification are routed to an escalation path rather than returned as a
guess.

```
HTTP → ClassifyProduct use case → RetrievalPort → LLMRerankPort → Verification gate → result | escalate
```

## How we got to 63.3% top-3 (and why it's stuck there)

| ADR | Decision | Result |
|---|---|---|
| [0001](docs/adr/0001-chapter-selection.md) | Scope v1 to TIPI Chapter 22 (beverages) | 34 NCMs, author domain expertise for eval labeling |
| [0002](docs/adr/0002-verification-deterministic-check.md) | Deterministic TIPI metadata check instead of a second LLM call | Zero-cost, testable structural guardrail |
| [0003](docs/adr/0003-walking-skeleton.md) | Walking skeleton (naive retrieval, passthrough rerank) | Baseline: 3.3% top-1 / 16.7% top-3 |
| [0004](docs/adr/0004-semantic-retrieval-e5-small.md) | Dense retrieval via `multilingual-e5-small` + ChromaDB | **33.3% top-1 / 63.3% top-3** — current production baseline |
| [0005](docs/adr/0005-hierarchical-enrichment.md) | Try injecting heading + subheading context into documents | **Rejected** — net regression to 53.3% top-3 (sibling homogenization) |
| [0006](docs/adr/0006-subheading-only-enrichment.md) | Try injecting only the narrow subheading | **Rejected** — same 53.3% ceiling; refutes the "level" hypothesis |
| [0007](docs/adr/0007-selective-enrichment-rejected.md) | Selective enrichment via a product-vs-refinement discriminator | **Rejected without implementation** — structural analysis showed a ceiling at ~63.3% (a tie), not worth measuring. Closes the enrichment line. |

**Root finding (ADR-0007):** the bottleneck isn't missing document
context — it's the discriminative power of the embedding model between
similar sibling products. Three rounds of text manipulation confirmed
this without touching the embedder itself.

**Next step (ADR-0008, planned):** swap `multilingual-e5-small` for
`bge-m3` — offline, zero recurring cost, stronger multilingual retrieval
— measured against the same 63.3% baseline. If that's insufficient, the
cost-ordered path forward is a cheap embedding API call, then LLM rerank
as the last (and most expensive) resort.

## Engineering discipline

- **Eval-first**: every retrieval/rerank change ships with a before/after
  delta against `eval/v1_cases.json` (30 labeled cases, hand-verified by
  the author against TIPI).
- **One variable per experiment**: each ADR isolates a single change so
  deltas compound legibly.
- **Pre-registered predictions**: hypotheses are written down before
  measuring, and reported honestly even when wrong (ADR-0005, ADR-0006).
- **Termination clause**: a pre-armed rule closed the enrichment line on
  structural evidence after three negative results, rather than letting
  it drift on sunk cost.
- **CI**: GitHub Actions gate on the production path (`OFF` strategy,
  63.3% baseline); experimental strategies are reproducible locally via
  `make eval-full` / `make eval-subheading` but don't run in CI.

## Install (development)

Semantic retrieval depends on `sentence-transformers` + `torch`. Install
PyTorch CPU-only first, from its dedicated index, so the ~2GB CUDA wheel
is never pulled on Linux:

```bash
# 1. PyTorch CPU-only (use --index-url, not --extra-index-url)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2. Project with dev + ml extras (torch already satisfied)
pip install -e ".[dev,ml]"
```

The base install (`pip install -e ".[dev]"`) stays light; the `ml` extra
is only needed to build the ChromaDB index and run the classifier
end-to-end.

```bash
make index   # build the ChromaDB index (required before eval/serve)
make eval    # run the 30-case eval suite against the production baseline
```

## Project structure

```
src/
  retrieval/      # RetrievalPort + adapters (naive, Chroma/e5-small)
  llm/             # LLMRerankPort + adapters (passthrough, ...)
  verification.py # deterministic TIPI structural check
  api/             # composition root + HTTP endpoint
docs/adr/          # decision log (start here)
eval/              # labeled cases + eval runner
data/tipi/         # TIPI Chapter 22 reference data
```

## See also

- `CLAUDE.md` — architecture, constraints, and decision-log conventions.
- `docs/adr/` — full ADR series, including per-case analysis data.
