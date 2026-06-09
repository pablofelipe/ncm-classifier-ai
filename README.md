# NCM Classifier AI

[![eval](https://github.com/pablofelipe/ncm-classifier-ai/actions/workflows/eval.yml/badge.svg)](https://github.com/pablofelipe/ncm-classifier-ai/actions/workflows/eval.yml)

RAG pipeline for classifying Brazilian products into NCM codes (Nomenclatura Comum do Mercosul), grounded on the official TIPI table.

See [CLAUDE.md](CLAUDE.md) for architecture, constraints, and decision log.

## Status

v1 in development — Chapter 22 (Beverages, spirits and vinegar).

## Metrics

<!-- Updated by CI after each eval run -->

| Metric | Target | Current |
|--------|--------|---------|
| Top-1 accuracy | ≥ 70% | — |
| Top-3 accuracy | ≥ 90% | — |
| ECE | ≤ 0.15 | — |
| Median latency | ≤ 4s | — |
| Cost / classification | ≤ R$ 0.10 | — |
