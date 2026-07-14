# Status

Current state, at a glance — not a roadmap. See [ROADMAP.md](ROADMAP.md) for
what's planned next, and [docs/adr/](docs/adr/) for why each decision was made.

| Area | Status |
|---|---|
| Dense retrieval (e5-small) | ✅ |
| Hybrid retrieval (BM25 + e5, opt-in) | ✅ |
| LLM rerank (provider-agnostic, Gemini implemented) | ✅ |
| BYOK — per-request LLM credentials | ✅ |
| Verification gate (existence + hierarchy) | ✅ |
| Corpus v2 (beverages, Ch.20/21/22) | ✅ |
| Corpus beyond beverages | ⏳ |
| Confidence calibration (ECE) | ⏳ |
| Public deployment (Docker / Fly.io) | 🚧 |
| API hardening (rate limiting, clean provider-error responses) | ⏳ |
| Observability (logging, metrics) | ⏳ |
| Project documentation (roadmap / status / deployment guide) | ✅ |

✅ done · 🚧 decided and in progress · ⏳ not started
