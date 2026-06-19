# NCM Classifier AI

A RAG pipeline that classifies Brazilian products into 8-digit NCM
(Nomenclatura Comum do Mercosul) fiscal codes, grounded on the official
TIPI table.

This repository is a portfolio project built under one constraint:
**every architectural decision is measured, not assumed.** Each change
to the retrieval pipeline is reported as an ADR with a before/after eval
delta — including the changes that didn't work. The decision log below
is the most useful part of this repo.

## Status

**Research / Experimental — active development.** The system does not yet
meet the v1 accuracy target; the deliverable so far is the **method** and
the decision log, not the headline numbers.

Active baseline — `multilingual-e5-small`, `OFF` strategy. The honest metric is
now the 350-case **v2** set (Ch.20/21/22, mode-tagged); the 30-case **v1** set
stays frozen for retroactive ADR comparison.

| Metric | v2 baseline (350) | v2 target | v1 (frozen, 30) | v1 target (v1 only) |
|---|---|---|---|---|
| Top-1 accuracy | 20.3% (71/350) | ≥ 40% | 33.3% (10/30) | ≥ 70% |
| Top-3 accuracy | **32.6% (114/350)** | ≥ 65% | **63.3% (19/30)** | ≥ 90% |
| ECE | uncalibrated (Passthrough rerank) | ≤ 0.15 | 0.54 | — |
| Median latency | within budget | ≤ 4s | within budget | — |
| Cost / classification | within budget | ≤ R$ 0.10 | within budget | — |

Eight ADRs narrowed the problem from "which text do we feed the model" to
"query understanding and ranking between similar products" — and proved, on
evidence, that **offline manipulation (document text *and* embedder) caps out
around 63% top-3 on v1.** ADR-0009 then widened the measurement surface: on 350
multi-chapter, mode-tagged cases the honest baseline is **32.6% top-3**, with
**colloquial/brand input the dominant hole** (20.5% top-3). The decision log
below is the most useful part of this repo.

### Dataset & corpus

| | v1 (frozen) | v2 (baseline: ADR-0009) |
|---|---|---|
| Eval cases | 30 (Chapter 22) | 350 (Ch.20/21/22), tagged by `mode` |
| Corpus | 34 NCMs (Ch.22) | 64 NCMs (Ch.20/21/22) |
| Role | historical baseline, comparable across ADRs 0003-0008 | honest baseline (32.6% top-3); surface for ADR-0010 onward |

v1 stays **frozen** so every ADR delta remains comparable. v2 widens the
measurement surface — 350 cases over juices (Ch.20/2009), coffee/tea
preparations (Ch.21) and beverages (Ch.22), each tagged with a `mode`
(colloquial / poverty / negation / frontier / multi-attr / direct) that
isolates the *query-understanding* failures. CI still gates on v1; v2 runs
locally (`make eval-v2`).

## Architecture

Hexagonal / ports-and-adapters. Retrieval and rerank are swappable
adapters behind `RetrievalPort` and `LLMRerankPort`, validated by two
implementations each (naive baseline + production adapter).

> ⚠️ **Planned — not yet integrated.** A **deterministic verification gate**
> (ADR-0002) is implemented and unit-tested in
> `src/core/verification/deterministic.py` (existence, chapter coherence,
> hierarchy consistency), but it is **not yet wired into the pipeline**: the
> shipping flow is retrieval → rerank → confidence gate, with no verification
> step. It was chosen over a second LLM call because it's testable, has zero
> marginal cost, and produces an auditable rejection reason; wiring it in (with
> failures routed to an escalation path) is planned for a future ADR.

```
HTTP → ClassifyProduct use case → RetrievalPort → LLMRerankPort → confidence gate → result
                                                              (Verification gate → escalate: planned, not yet wired)
```

Two infrastructure seams make experimentation cheap and reproducible without
re-implementing the pipeline:

- **`EnrichStrategy`** (enum) — selects the document text strategy (`OFF` /
  `FULL` / `SUBHEADING_ONLY`) at index time; the adapter refuses an
  index↔strategy mismatch.
- **`EmbedderModel`** (enum) + `make_embedding_function` factory — the embedder
  is swappable (`e5_small` default, `bge_m3` opt-in) and recorded in the
  collection metadata; the same guard refuses an index↔embedder mismatch.

Both are wired through `Settings` (env: `ENRICH_STRATEGY`, `EMBEDDER`), so an
experiment is a config flag plus a rebuild, not a code change.

## Decision log — eight ADRs, what worked, what didn't, and why

| ADR | Title | Status | Central finding |
|---|---|---|---|
| [0001](docs/adr/0001-chapter-selection.md) | Chapter 22 scope | Accepted | 34 NCMs; author domain expertise for eval labeling |
| [0002](docs/adr/0002-verification-deterministic-check.md) | Deterministic verification | Accepted | TIPI metadata check beats a 2nd LLM call: zero-cost, testable, auditable |
| [0003](docs/adr/0003-walking-skeleton.md) | Walking skeleton | Accepted | Naive retrieval + passthrough: 3.3% top-1 / 16.7% top-3 baseline |
| [0004](docs/adr/0004-semantic-retrieval-e5-small.md) | Dense retrieval (e5-small) | **Accepted (ships)** | `multilingual-e5-small` + ChromaDB: **33.3% / 63.3%** — the production baseline |
| [0005](docs/adr/0005-hierarchical-enrichment.md) | Hierarchical enrichment | Rejected | Heading+subheading context → net regression to 53.3% (sibling homogenization) |
| [0006](docs/adr/0006-subheading-only-enrichment.md) | Subheading-only enrichment | Rejected | Same 53.3% ceiling; refutes the "which level" hypothesis |
| [0007](docs/adr/0007-selective-enrichment-rejected.md) | Selective enrichment | Rejected (unmeasured) | Structural ceiling at ~63.3%; bottleneck is embedder discrimination, not context. Closes the enrichment line |
| [0008](docs/adr/0008-embedder-swap-bge-m3-rejected.md) | Embedder swap (bge-m3) | Rejected | bge-m3 regressed (OFF 43.3%, FULL 53.3%); e5 OFF unbeaten. Closes the offline retrieval-quality line. Infra kept (configurable embedder + guard) |
| [0009](docs/adr/0009-dataset-corpus-expansion-v2-baseline.md) | Dataset + corpus expansion (v2 baseline) | **Accepted** | 350 cases / 64 NCMs (Ch.20/21/22), mode-tagged. e5 OFF v2 baseline **20.3% / 32.6%**; colloquial the dominant hole (20.5%). Recalibrated targets (≥40% / ≥65%); opens ADR-0010 |

**Root finding (ADRs 0005-0008):** offline manipulation — of the document text
*or* of the embedder — is exhausted at ~63% top-3. Even bge-m3, a top
multilingual retrieval model, regressed. The remaining failures are
**query-understanding** (colloquial/brand input) and **ranking precision**, not
document representation.

**Path forward (cost-ordered, rerank last):** ADR-0009 set the v2 baseline
(32.6% top-3); next is **ADR-0010** corpus enrichment (synonyms, brands —
attacks the colloquial hole) → **ADR-0011** BM25 + e5 hybrid retrieval →
**ADR-0012** local cross-encoder rerank (zero recurring cost) → **ADR-0013**
LLM rerank (last resort, recurring cost, must clear the R$ 0.10 / 4 s budget).

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

### Running tests

```bash
make test              # unit tests only (tests/unit)
make test-integration  # integration tests (downloads models, requires network)
```

`make test` runs unit tests only. Use `make test-integration` for the
integration tests, which download the embedding models and require network.

### Running evals

```bash
# v1 — 30 cases, Chapter 22, the production baseline (also what CI runs)
make index      # build the ChromaDB index (required before eval/serve)
make eval-v1    # == make eval; reports 33.3% top-1 / 63.3% top-3

# v2 — 350 cases over the expanded Ch.20/21/22 corpus (local only)
make index-v2   # build the isolated tipi_capbeverage collection (64 NCMs)
make eval-v2    # run the 350-case suite (per-difficulty + per-mode breakdown)
```

`make eval` (no suffix) stays pinned to v1 so CI is unaffected. The v2 targets
set `NCM_CHAPTER=beverage`, which points retrieval at the isolated
`tipi_capbeverage` collection and the v2 loader at `tipi_beverage_*.json`.

## Project structure

```
src/
  core/                      # domain + application (no framework imports)
    domain/                  # ncm, enrichment, tipi_parsing
    ports.py                 # RetrievalPort, LLMRerankPort
    use_cases/               # classify_product
    verification/            # deterministic.py — deterministic TIPI check (planned, not yet wired)
  retrieval/                 # RetrievalPort adapters (naive, Chroma/e5-small) + embedding
  llm/                       # LLMRerankPort adapters (passthrough; gemini_client stub)
  api/                       # composition root + HTTP endpoint
  config.py                  # Settings (EnrichStrategy, EmbedderModel)
  main.py                    # FastAPI app entrypoint
docs/adr/                    # decision log (start here)
eval/                        # v1_cases.json (30) + v2_cases.json (350) + eval runner
data/tipi/                   # TIPI reference data (Ch.22; beverage = Ch.20/21/22)
scripts/                     # ingest_tipi.py — XLSX → corpus JSON (incl. `beverage`)
```

## See also

- `CLAUDE.md` — architecture, constraints, and decision-log conventions.
- `docs/adr/` — full ADR series, including per-case analysis data.
