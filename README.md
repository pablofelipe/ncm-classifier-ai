# NCM Classifier AI

[![eval](https://github.com/pablofelipe/ncm-classifier-ai/actions/workflows/eval.yml/badge.svg)](https://github.com/pablofelipe/ncm-classifier-ai/actions/workflows/eval.yml)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

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
stays frozen for retroactive ADR comparison. The v2 column below is **hybrid
retrieval + Gemini Flash rerank** (BM25 + e5 via RRF, ADR-0011; Gemini 2.5 Flash
rerank, ADR-0013; opt-in `RETRIEVAL_MODE=hybrid RERANK_MODE=gemini`).

| Metric | v2 (350, ADR-0013 hybrid+Gemini) | v2 target | v1 (frozen, 30) | v1 target (v1 only) |
|---|---|---|---|---|
| Top-1 accuracy | **71.7% (251/350)** | ≥ 40% ✓ | 33.3% (10/30) | ≥ 70% |
| Top-3 accuracy | **75.7% (265/350)** | ≥ 65% ✓ | **63.3% (19/30)** | ≥ 90% |
| ECE | uncalibrated | ≤ 0.15 | 0.54 | — |
| Median latency | ~2.1 s/query | ≤ 4s | within budget | — |
| Cost / classification | ~R$ 0.00013 | ≤ R$ 0.10 | within budget | — |

Thirteen ADRs narrowed the problem from "which text do we feed the model" to
"query understanding and ranking between similar products" — and proved, on
evidence, that **offline manipulation (document text *and* embedder) caps out
around 63% top-3 on v1.** ADR-0009 then widened the measurement surface: on 350
multi-chapter, mode-tagged cases the honest baseline was **32.6% top-3**, with
**colloquial/brand input the dominant hole** (20.5% top-3). ADR-0010 attacked
that hole with a corpus-synonyms file (brands + colloquial names): colloquial
top-3 jumped 20.5% → 59.1% and the aggregate rose to 51.7% top-3. ADR-0011
fused BM25 with e5 via RRF — clearing **both v2 targets** at **49.1% / 68.0%**
(colloquial 85.0%). ADR-0012 (local cross-encoder) was rejected due to domain
gap (−29 pp). ADR-0013 added Gemini 2.5 Flash rerank — an instruction-following
LLM that reasons over fiscal nomenclature without fine-tuning — reaching
**71.7% top-1 / 75.7% top-3** (+22.6 / +7.7 pp), with negation and frontier
modes showing the largest gains. The decision log below is the most useful part
of this repo.

### Dataset & corpus

| | v1 (frozen) | v2 (baseline: ADR-0009) |
|---|---|---|
| Eval cases | 30 (Chapter 22) | 350 (Ch.20/21/22), tagged by `mode` |
| Corpus | 34 NCMs (Ch.22) | 64 NCMs (Ch.20/21/22) |
| Best config | dense, PASSTHROUGH | hybrid + Gemini Flash rerank (ADR-0013) |
| Role | historical baseline, comparable across ADRs 0003-0008 | honest surface (ADR-0009 32.6% → ADR-0010 51.7% → ADR-0011 hybrid 68.0% top-3); the measurement target for ADR-0010 onward |

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

A **deterministic verification gate** (ADR-0002, wired in ADR-0014) runs after
rerank in `src/core/verification/deterministic.py`: existence and hierarchy
consistency against the loaded TIPI index. Chapter coherence was dropped at
wiring time (ADR-0014) — a fixed expected chapter doesn't fit the multi-chapter
v2 corpus, and existence already covers the equivalent case. It was chosen over
a second LLM call because it's testable, has zero marginal cost, and produces
an auditable rejection reason. A failing verification forces
`confidence_label="needs_review"` and sets `escalation_reason` to the failure
status, regardless of the rerank score; it never changes which candidates are
returned.

```
HTTP → ClassifyProduct use case → RetrievalPort → LLMRerankPort → confidence gate + verification gate → result
                                                        ↑
                                        GenericLLMRerankAdapter → LLMClient → GeminiClient
```

**LLM rerank is provider-agnostic (ADR-0016).** `LLMRerankPort` — the domain's
only view of reranking — never changed. Behind it, `GenericLLMRerankAdapter`
holds the (vendor-neutral) prompt/parsing logic and talks to an injected
`LLMClient` — a small capability contract (`generate(model, system_instruction,
prompt, response_format)`), not a specific SDK shape. `GeminiClient` is the only
implementation today; adding OpenAI/Anthropic/DeepSeek is a new `LLMClient` plus
one entry in `resolve_llm_client`'s provider dict, with no change to `core/`,
the use case, or the composition root's branching. Reached via
`RERANK_MODE=gemini` (server-side `LLM_PROVIDER`/`LLM_MODEL` + `GEMINI_API_KEY`,
opt-in) **or** a per-request `X-LLM-Api-Key` header (see below) — whichever
resolves first at the composition root wins for that one request.

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

### Bring Your Own LLM Credentials

The public deployment of this API ships with **no LLM credential of its own**
— `GEMINI_API_KEY` is never set in its environment, and `RERANK_MODE` runs
whatever the server-side default is there (Passthrough or hybrid retrieval,
zero LLM cost). This is a deliberate property, not an oversight: a public
portfolio demo must never let a visitor's traffic spend the maintainer's own
API budget.

To see the LLM-rerank path (the flagship 71.7%/75.7% result) live, send your
own credential in a request header — it's used only for that one call, never
persisted, logged, or cached:

```bash
curl -X POST https://<public-url>/classify \
  -H "Content-Type: application/json" \
  -H "X-LLM-Api-Key: <your-gemini-api-key>" \
  -d '{"product_name": "agua mineral", "description": "garrafa 500ml"}'
```

`LLM-Provider` and `LLM-Model` are optional refinements (default to the
server's `LLM_PROVIDER`/`LLM_MODEL`, currently `google` / `gemini-2.5-flash`
— the only provider implemented so far):

```bash
curl -X POST https://<public-url>/classify \
  -H "Content-Type: application/json" \
  -H "X-LLM-Api-Key: <your-gemini-api-key>" \
  -H "LLM-Provider: google" \
  -H "LLM-Model: gemini-2.5-pro" \
  -d '{"product_name": "agua mineral", "description": "garrafa 500ml"}'
```

Without `X-LLM-Api-Key`, `LLM-Provider`/`LLM-Model` are ignored entirely —
sending them alone can never trigger a call on the server's credentials
(there are none). See ADR-0016 for the full design.

## Decision log — fifteen ADRs, what worked, what didn't, and why

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
| [0010](docs/adr/0010-corpus-enrichment-synonyms.md) | Corpus enrichment (synonyms) | **Accepted (ships on v2)** | Synonyms file (22 NCMs, 129 terms, evidence-bound) appended to OFF docs; v1 blindado. v2 **20.3%→30.9% / 32.6%→51.7%** (+19.1 pp top-3); colloquial 20.5%→59.1%. multi_attr flat; opens ADR-0011 |
| [0011](docs/adr/0011-hybrid-retrieval-bm25-rrf.md) | Hybrid retrieval (BM25 + e5, RRF) | **Accepted (opt-in on v2)** | BM25 over the same Chroma docs, fused with e5 via RRF (k=60); `RETRIEVAL_MODE` default DENSE. v2 **30.9%→49.1% / 51.7%→68.0%** — first to clear **both** targets. colloquial 59.1%→85.0% (synonyms + BM25 compound); opens ADR-0012 |
| [0012](docs/adr/0012-cross-encoder-rerank-rejected.md) | Local cross-encoder rerank (mmarco-mMiniLMv2) | **Rejected** | `RERANK_MODE=cross_encoder` on ADR-0011 baseline: **49.1%→20.3% / 68.0%→38.6%** (−28.8/−29.4 pp). Domain gap: mMARCO cross-encoder trained on web QA pairs; TIPI descriptions are 2-8 token fiscal nomenclature — model produces near-random logits. Colloquial 85.0%→43.3% (ADR-0010/0011 compounding gain destroyed). Infrastructure kept; production `PASSTHROUGH`; opens ADR-0013 |
| [0013](docs/adr/0013-gemini-flash-rerank.md) | Gemini 2.5 Flash LLM rerank | **Accepted (ships on v2)** | `RERANK_MODE=gemini`, top-5 pool, PT-BR fiscal prompt, `response_mime_type=application/json`, logged fallback. ADR-0011 baseline: **49.1%→71.7% / 68.0%→75.7%** (+22.6/+7.7 pp). Top-1/top-3 gap collapsed 18.9 pp → 4.0 pp. Negation +23.4 pp, frontier +21.7 pp (LLM reasons over fiscal semantics without fine-tuning). 0 JSON fallbacks. Cost: R$ 0.00013/query (770× below budget). Latency: ~2.1 s/query. Both v2 targets met with margin; top-1 exceeds v1 target (≥70%) on v2 corpus |
| [0014](docs/adr/0014-verification-gate-wiring-chapter-coherence-dropped.md) | Verification gate wiring (chapter-coherence dropped) | **Accepted (ships)** | ADR-0002's deterministic check finally wired into `ClassifyProduct` after rerank. Fixed `expected_chapter` doesn't fit the multi-chapter v2 corpus (`NCM_CHAPTER=beverage` spans Ch.20/21/22) — dropped in favor of existence + hierarchy-consistency only, since existence already subsumes the chapter check for a corpus-scoped index. Failing verification forces `needs_review` and sets `escalation_reason`, regardless of rerank score; candidates returned are unchanged |
| [0016](docs/adr/0016-provider-agnostic-llm-integration.md) | Provider-agnostic LLM integration | **Accepted (ships)** | `LLMRerankPort` unchanged; `GenericLLMRerankAdapter` + `LLMClient` (`GeminiClient` today) + `resolve_llm_client` decouple rerank from any vendor. `LLM_PROVIDER`/`LLM_MODEL` replace Gemini-specific config. Per-request `X-LLM-Api-Key`/`LLM-Provider`/`LLM-Model` headers let a visitor supply their own credential — used only for that call, never persisted/logged/cached — so the public deployment carries no server-side LLM key at all. 30-case stratified parity check: identical top-1/top-3 before/after the cutover (full 350-case confirmation pending, deferred by Gemini API instability during measurement) |

**Root finding (ADRs 0005-0008):** offline manipulation — of the document text
*or* of the embedder — is exhausted at ~63% top-3. Even bge-m3, a top
multilingual retrieval model, regressed. The remaining failures are
**query-understanding** (colloquial/brand input) and **ranking precision**, not
document representation.

**Path completed (ADRs 0009–0013):** ADR-0009 set the v2 baseline (32.6% top-3);
**ADR-0010** synonyms closed the colloquial hole (20.5% → 59.1%, aggregate 51.7%);
**ADR-0011** BM25+e5 hybrid hit **49.1% / 68.0%** (colloquial 85.0%); **ADR-0012**
cross-encoder rejected (domain gap, −29 pp); **ADR-0013** Gemini Flash rerank
reached **71.7% / 75.7%** — all v2 targets met with margin; **ADR-0014** wired
the deterministic verification gate (ADR-0002) into the pipeline, dropping the
chapter-coherence check as ill-fitting for the multi-chapter corpus; **ADR-0016**
made LLM rerank provider-agnostic and added per-request "bring your own
credentials" headers, so a public deployment can run with no server-side LLM
key at all. Remaining gaps: `frontier` 65.2% top-3, `hard` 63.8% top-3 (correct
NCM not in top-5 retrieval pool — retrieval limit, not rerank limit). Logical
next steps: expand corpus beyond beverages; calibrate confidence scores (ECE);
public deployment (Fly.io/Railway).

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
- **AI-assisted, same rules**: parts of this codebase are written with AI
  coding agents. They operate under the same discipline as manual work —
  TDD and hexagonal-boundary rules are encoded as enforced agent skills
  (`.claude/skills/`), and every resulting change still has to clear the
  same eval gate as any other.
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
    verification/            # deterministic.py — deterministic TIPI check, wired into ClassifyProduct (ADR-0014)
  retrieval/                 # RetrievalPort adapters (naive, Chroma/e5-small) + embedding
  llm/                       # LLMRerankPort adapters (passthrough, cross-encoder,
                              #   generic_llm_rerank_adapter.py) + llm_client.py
                              #   (LLMClient protocol + resolve_llm_client factory,
                              #   ADR-0016) + gemini_client.py (GeminiClient)
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

## License

Licensed under the [Apache License 2.0](LICENSE).
