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
| Production Docker image (baked index, non-root, offline model cache) | ✅ |
| Operational endpoints (`/`, `/health`, `/version`, `/info`) | ✅ |
| OpenAPI/Swagger documentation (descriptions, examples, BYOK headers documented) | ✅ |
| Fly.io config (`fly.toml` — scale-to-zero, health check, BYOK-safe) | ✅ |
| Fly.io live deploy (actual public URL) | ⏳ |
| API hardening (rate limit, clean provider errors, CORS, security headers, payload cap, provider timeout) | ✅ |
| Observability (structured logging, metrics) | ⏳ |
| Project documentation (roadmap / status / deployment guide) | ✅ |

✅ done · 🚧 decided and in progress · ⏳ not started
