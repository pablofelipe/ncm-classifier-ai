# NCM Classifier AI

[![eval](https://github.com/pablofelipe/ncm-classifier-ai/actions/workflows/eval.yml/badge.svg)](https://github.com/pablofelipe/ncm-classifier-ai/actions/workflows/eval.yml)

RAG pipeline for classifying Brazilian products into NCM codes (Nomenclatura Comum do Mercosul), grounded on the official TIPI table.

See [CLAUDE.md](CLAUDE.md) for architecture, constraints, and decision log.

## Status

v1 in development — Chapter 22 (Beverages, spirits and vinegar).

## Install (development)

Semantic retrieval (ADR-0004) depends on `sentence-transformers` + `torch`.
Install PyTorch CPU-only **first**, from its dedicated index, so the ~2 GB CUDA
wheel is never pulled on Linux:

```bash
# 1. PyTorch CPU-only (use --index-url, not --extra-index-url)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2. Project with dev + ml extras (torch is already satisfied, not reinstalled)
pip install -e ".[dev,ml]"
```

The base install (`pip install -e ".[dev]"`) stays light; the `ml` extra is only
needed to build the ChromaDB index and run the classifier end-to-end.

> **TODO (revisit in ADR-0004):** local dev currently runs on Python 3.14 while
> CI pins 3.13 (`requires-python >=3.13`). Not yet reconciled — torch publishes
> wheels for both, but the version split should be made explicit (pin a single
> dev version, or test a matrix) before the eval baseline is locked.

## Metrics

<!-- Updated by CI after each eval run -->

| Metric | Target | Current |
|--------|--------|---------|
| Top-1 accuracy | ≥ 70% | — |
| Top-3 accuracy | ≥ 90% | — |
| ECE | ≤ 0.15 | — |
| Median latency | ≤ 4s | — |
| Cost / classification | ≤ R$ 0.10 | — |
