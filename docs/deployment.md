# Deployment

Operational guide: how to run this system, not what it is or why it's built
this way. See the [README](../README.md) for the architecture and the
decision log, and [ROADMAP.md](../ROADMAP.md) for what in this guide is still
aspirational.

## Local development

```bash
# 1. PyTorch CPU-only first (use --index-url, not --extra-index-url,
#    so the ~2GB CUDA wheel is never pulled)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 2. Project with dev + ml extras
pip install -e ".[dev,ml]"

# 3. Environment
cp .env.example .env
# GEMINI_API_KEY is optional — leave unset to run Passthrough rerank
# (zero LLM cost). Only needed for RERANK_MODE=gemini locally.

# 4. Build the ChromaDB index (production chapter, Ch.22)
make index

# 5. Run the API
make run   # uvicorn src.main:app --reload --port 8000
```

To exercise the v2 corpus (350 cases, Ch.20/21/22) instead of the production
Ch.22 baseline:

```bash
make index-v2   # builds the isolated tipi_capbeverage collection
NCM_CHAPTER=beverage make run
```

Running tests and evals is documented in the [README](../README.md#running-tests)
— this guide only covers getting a live instance up.

## Docker

Generic on purpose — nothing Fly.io-specific lives in the `Dockerfile` or
here. Any platform that can run a container and probe `GET /health` can run
this image unchanged (see [ROADMAP.md](../ROADMAP.md), Deployment pillar).

```bash
make docker-build   # docker build -t ncm-classifier .
make docker-run     # docker run --rm -p 8000:8000 ncm-classifier
```

```bash
curl http://localhost:8000/health
curl http://localhost:8000/version
curl http://localhost:8000/info
```

What's baked into the image at build time (ADR-0015 — "a deploy is a
build"), so the container never touches the network or rebuilds anything at
request time:

- The ChromaDB index for the **Default Public Deployment Profile**: the
  beverage corpus (ADR-0009, 64 NCMs, Ch.20/21/22), synonyms-enriched
  (ADR-0010), served with `RETRIEVAL_MODE=hybrid` (ADR-0011) and
  `RERANK_MODE=passthrough` by default — chosen for being deterministic,
  reproducible and zero recurring cost, not for being the single highest
  score. Your own `X-LLM-Api-Key` still reaches the stronger Gemini-rerank
  result (ADR-0013) on top of this same index.
- The `multilingual-e5-small` model weights themselves — `embed_query()` runs
  on every retrieval call (not just at index-build time), so the model cache
  is baked in too and the runtime image sets `HF_HUB_OFFLINE=1` /
  `TRANSFORMERS_OFFLINE=1`: a request never attempts a HuggingFace network
  call, only ever reads the baked cache.
- No persistent volume anywhere — a fresh container from this image tag is a
  fully self-contained, reproducible snapshot of code *and* data.

Other properties, already validated (build + real `docker run`, not just
read from the Dockerfile):

- Multi-stage build; runs as a fixed non-root user (`app`, uid/gid 1000).
- Respects `$PORT` (Cloud Run/Railway inject it; Fly.io and plain `docker
  run` are fine with the default 8000) — e.g. `docker run --rm -e PORT=9000
  -p 9000:9000 ncm-classifier`.
- A native Docker `HEALTHCHECK` against `GET /health` — no curl/wget
  dependency added, works the same under any orchestrator.
- Image size is **~3.1GB** — large because `torch`/`sentence-transformers`
  and the baked model cache are genuine runtime dependencies (query
  embedding happens per-request), not build-time-only. "Generic and
  reproducible" was the goal here, not "minimal footprint."

## Deploy

**Not currently live.** `ncm-classifier-ai` ran successfully in production
on Fly.io (v0.2.0) for about an hour, then was torn down while
investigating how it had been created — see
[docs/operational-notes.md](operational-notes.md) for both the port
mismatch that came up during that deploy and the account-level
`unauthorized` error currently blocking recreating the app (needs the
maintainer to check Fly.io Billing/Organization settings before
`flyctl launch` can create an app again). `fly.toml`/`Dockerfile` need no
changes — this is the same config that ran successfully before.

What `fly.toml` configures, once deployed:

- **`primary_region = "gru"`** (São Paulo) — closest Fly.io region to this
  project's domain (Brazilian NCM/TIPI data). Change if deploying from/for a
  different audience.
- **Scale-to-zero**: `auto_stop_machines`/`auto_start_machines` on,
  `min_machines_running = 0` — the instance suspends when idle and wakes on
  request, so sparse demo traffic costs close to nothing while unused.
- **Health check** against the same `GET /health` the Dockerfile's own
  `HEALTHCHECK` already probes — this one is what Fly's proxy/scheduler uses
  to decide whether a machine is ready and whether to restart it.
- **`[[vm]]` sizing** (`shared-cpu-2x`, 2GB) is a starting guess for the
  CPU-bound e5-small query embedding, not a measured optimum — revisit once
  there's real traffic (ROADMAP.md, Performance pillar).
- **No `[env]` section, deliberately** — `NCM_CHAPTER`/`RETRIEVAL_MODE`/
  `RERANK_MODE` are already baked as Dockerfile defaults (the Default Public
  Deployment Profile, Etapa 3); repeating them in `fly.toml` would just be a
  second place to drift out of sync.
- **No `GEMINI_API_KEY` secret, ever, on this app** — the file has a comment
  saying so explicitly. The public instance holds no LLM credential of its
  own (ADR-0015); visitors bring their own via `X-LLM-Api-Key`
  (ADR-0016), which `fly.toml` never touches.

## Hardening

Applied at the app level (`src/main.py`, `src/api/`), so it's active locally
and in Docker already — not something that only exists once Fly.io is live.

- **Rate limit**: `POST /classify` only (never `/health`, `/version`,
  `/info` — Fly's own health check must never be throttled), 20
  requests/IP/minute by default (`RATE_LIMIT_PER_MINUTE`), in-memory and
  per-process. A distributed limiter (Redis, etc.) is deliberately not used —
  the deployment is a single scale-to-zero machine (ADR-0015), not a fleet;
  see `ROADMAP.md` if that ever changes. Exceeding it returns `429` with a
  `Retry-After` header.
- **Clean provider errors**: an invalid visitor `X-LLM-Api-Key` (or any
  provider-side rejection) now returns `422` (bad credential/request) or
  `502` (provider outage), with a fixed generic message — never a stack
  trace, never the provider's raw response (ADR-0016 Consequences, closed).
- **Provider request timeout**: the Gemini SDK client is built with a bounded
  15s timeout — previously unbounded, a stuck upstream connection could hold
  a request open indefinitely.
- **CORS**: open (`allow_origins=["*"]`), explicitly allowing the BYOK
  headers (`X-LLM-Api-Key`, `LLM-Provider`, `LLM-Model`) so a browser-based
  client can send them cross-origin. Safe here specifically because this API
  has no cookies or session state to leak — "anyone can try it" (ADR-0015) is
  the point.
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Strict-Transport-Security` on every response. No CSP —
  this is a JSON API with no HTML to constrain.
- **Payload cap**: requests over 10KB are rejected (`413`) before the body is
  even parsed — `schemas.py`'s per-field `max_length` only rejects *after*
  the whole body is already in memory.
- **Not done, deliberately**: response compression. Payloads here are a few
  hundred bytes to a couple KB (a handful of NCM candidates); gzip's CPU cost
  isn't justified at this size.

## Testing the API

`GET /` — landing page for first-time visitors (project name, version,
deployment profile label, and a pointer to the endpoints below); `GET /docs`
is the interactive Swagger UI, with descriptions and worked examples for
every endpoint and field (Release Polish):

```bash
curl http://localhost:8000/
open http://localhost:8000/docs  # or just visit it in a browser
```

`GET /health` — liveness check, no auth, no LLM call:

```bash
curl http://localhost:8000/health
```

`POST /classify` — without any LLM credential (Passthrough or hybrid
retrieval only, zero LLM cost):

```bash
curl -X POST http://localhost:8000/classify \
  -H "Content-Type: application/json" \
  -d '{"product_name": "agua mineral", "description": "garrafa 500ml"}'
```

`POST /classify` — with your own Gemini credential, to exercise the LLM
rerank path (the 71.7%/75.7% result from ADR-0013). The key is used only for
this one request, never persisted, logged, or cached (ADR-0016):

```bash
curl -X POST http://localhost:8000/classify \
  -H "Content-Type: application/json" \
  -H "X-LLM-Api-Key: <your-gemini-api-key>" \
  -d '{"product_name": "agua mineral", "description": "garrafa 500ml"}'
```

`LLM-Provider` / `LLM-Model` are optional refinements, only consulted when
`X-LLM-Api-Key` is present — sent alone, without a key, they're inert and
can never trigger a call on the server's own credentials:

```bash
curl -X POST http://localhost:8000/classify \
  -H "Content-Type: application/json" \
  -H "X-LLM-Api-Key: <your-gemini-api-key>" \
  -H "LLM-Provider: google" \
  -H "LLM-Model: gemini-2.5-pro" \
  -d '{"product_name": "agua mineral", "description": "garrafa 500ml"}'
```

An unknown `LLM-Provider` returns `422` with a clear message rather than a
silent fallback.

**Do not run these against a real Gemini key as part of an automated test or
smoke-test sweep without asking first** — actual API usage has a cost, and
this project's policy is to get explicit approval before any run that spends
real LLM budget.

## Costs

The public deployment holds **no LLM credential of its own** — `GEMINI_API_KEY`
is never set in its environment, by construction, not by convention (ADR-0016).
Its default path (Passthrough or hybrid retrieval) costs nothing per request
regardless of traffic volume.

A visitor who wants to see the LLM-rerank path live supplies their **own**
Gemini API key via the `X-LLM-Api-Key` header — that spends their own budget,
never the maintainer's. This is what makes a public, unauthenticated demo
viable without a recurring LLM bill: the only recurring cost is compute/hosting
(near-zero with scale-to-zero), not inference.
