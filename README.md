# NCM Classifier AI

RAG pipeline para classificação de produtos brasileiros em códigos NCM (Nomenclatura Comum do Mercosul), fundamentado na tabela TIPI oficial.

See [CLAUDE.md](CLAUDE.md) for architecture, constraints, and decision log.

## Status

v1 em desenvolvimento — Capítulo 22 (Bebidas, líquidos alcoólicos e vinagres).

## Metrics

<!-- Updated by CI after each eval run -->

| Metric | Target | Current |
|--------|--------|---------|
| Top-1 accuracy | ≥ 70% | — |
| Top-3 accuracy | ≥ 90% | — |
| ECE | ≤ 0.15 | — |
| Median latency | ≤ 4s | — |
| Cost / classification | ≤ R$ 0.10 | — |
