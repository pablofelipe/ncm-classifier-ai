# Operational Notes

Learnings from operating this system that don't rise to the level of an ADR
(no architectural decision changed) but are worth recording so they aren't
rediscovered the hard way again. See `docs/adr/` for actual architecture
decisions and `docs/deployment.md` for the how-to-run guide this complements.

## 2026-07-14 — `internal_port` mismatch on first Fly.io deploy

**What happened:** the first `fly launch` against this repo produced a live
app config with `internal_port: 8080`, while the Docker image (and
`fly.toml` as committed) actually serves on port 8000
(`ENV PORT=8000` in the `Dockerfile`, matching `fly.toml`'s
`http_service.internal_port = 8000`). Every health check failed
("the machine hasn't started"), and the public URL
(`https://ncm-classifier-ai.fly.dev`) didn't respond — Fly's proxy was
correctly forwarding to a port nothing in the container was listening on.

**Root cause:** `fly launch`'s interactive port-detection did not end up
matching the committed `fly.toml`. The exact trigger wasn't confirmed (it
can happen if `fly launch` re-scans the Dockerfile/prompts for a port
instead of trusting an existing `fly.toml`'s `internal_port`, depending on
flags and flyctl version), but the effect was clear and reproducible: the
app that got created had `8080` live, not `8000`.

**Fix:** running `fly deploy` from the repo re-applied the committed
`fly.toml` (with the correct `internal_port = 8000`) to the existing app,
which corrected the port on the next machine update. No code or
architecture change — the fix was making sure the *deployed* config matched
the *committed* config.

**Takeaway for future deploys:** after any `fly launch`, before trusting the
app is healthy, run `fly config show -a <app>` and diff it against the
repo's `fly.toml` — specifically `internal_port` — rather than assuming
`fly launch` faithfully copied it. `fly deploy` alone re-syncs config from
the repo, so when in doubt, a plain `fly deploy` is a safe way to force the
live config back in line with what's committed.

## 2026-07-14 — Cold-start latency on `POST /classify` (measured, resolved as expected behavior)

**Measurement:** the first `POST /classify` against a freshly-deployed
machine (scale-to-zero, `shared-cpu-2x`) took ~17.6s wall-clock, while the
response's own `latency_ms` field reported only ~2075ms. An immediate
second request completed in ~2.0s wall-clock, matching its own
`latency_ms` (~1840ms) almost exactly.

**Interpretation:** the ~15s gap on the first request is a one-time,
per-process cost — first import of `sentence-transformers`/`transformers`/
`chromadb` (torch initialization, etc.) and first read of the baked model
cache/index from the container's filesystem — paid once when the process
(re)starts, not on every request. It happens *before* `routes.py`'s
`time.perf_counter()` starts (inside dependency resolution,
`get_classify_use_case` → `build_classify_use_case`), so it never shows up
in `latency_ms`, only in end-to-end wall-clock time.

This refutes an initial hypothesis (recorded and discarded here rather than
silently dropped) that a new `E5EmbeddingFunction()` being constructed
per-request — it genuinely is, `build_classify_use_case` doesn't cache it
across requests — meant the model was being reloaded from disk on every
single call. The second request's timing shows that isn't the dominant
cost: whatever *is* per-instance about `E5EmbeddingFunction` construction
is cheap once the underlying libraries and files are warm in the process/
OS cache.

**Not a bug, not changed:** consistent with a scale-to-zero deployment —
the first request after any cold start (deploy, or waking from idle) pays
this cost, subsequent requests don't. If real traffic shows this matters
(e.g., the demo's very first visitor after a long idle period gets a slow
response), candidates to revisit — none applied, no decision made — are a
lightweight warm-up request on machine start, or `min_machines_running = 1`
(trades the near-zero-cost property for latency). Worth an ADR only if it
becomes an actual decision, not before.
