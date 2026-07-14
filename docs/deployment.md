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

**Not implemented yet** — tracked in [ROADMAP.md](../ROADMAP.md) (Deployment
pillar, P0). ADR-0015 decided the target shape; there is no `Dockerfile` in
the repo today. The planned flow, once built:

- A single-stage image with the `ml` extra installed and the ChromaDB index
  **baked in at build time** — no persistent volume, so a fresh container
  starts ready to serve without a rebuild step.
- No `GEMINI_API_KEY` (or any LLM credential) set in the image or its runtime
  environment — the public deployment constraint from ADR-0015.
- Build and run commands will be added here once the `Dockerfile` exists.

## Deploy

**Not implemented yet** — tracked in [ROADMAP.md](../ROADMAP.md) (Deployment
pillar, P0). ADR-0015 names Fly.io as the target; there is no `fly.toml` in
the repo today. The planned flow:

- Scale-to-zero, so the recurring cost with no traffic is near zero.
- The image described above (baked index, no LLM credential) is what gets
  deployed — the public instance never holds `GEMINI_API_KEY`.
- Rate limiting and clean provider-error handling (currently: an invalid
  visitor `X-LLM-Api-Key` surfaces as an unhandled `500`) are called out as
  P1 in the roadmap and are expected to land **before** the URL goes public,
  not after.

## Testing the API

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
