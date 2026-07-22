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

## 2026-07-14 — Fly.io account blocked from creating apps (not a token scope issue)

**What happened:** the app created above was destroyed (the maintainer had
originally created it by hand via the Fly.io dashboard to test, with the
port mismatch documented above; the plan was to destroy it and recreate
cleanly via `flyctl launch` from this repo). Recreating it failed with
`Error: unauthorized`, both via `flyctl launch`/`flyctl apps create` using
the configured `FLY_API_TOKEN` **and** when the maintainer ran the same
`flyctl apps create` command directly, locally authenticated (no token
involved). `flyctl tokens create org` also failed with
`Not authorized to access this createLimitedAccessToken`.

**Diagnosis:** since the failure reproduces for the account owner directly
(not just a scoped API token), this rules out a token-permission problem —
it points to an account/org-level restriction on Fly.io's side, most
commonly a missing payment method (Fly.io requires one on file before
provisioning new apps, even on usage that would stay within any free
allowance, as an anti-abuse measure). Not confirmed further — the fix
requires checking the Fly.io dashboard's Billing/Organization settings
directly, which is account access only the maintainer has.

**Resolved:** a new Fly.io org-scoped API token (generated after the
maintainer addressed the account-level restriction) fixed `flyctl launch`'s
app-creation step. One residual error persisted even with the new token —
`Error: failed creating token: ... createLimitedAccessToken Not authorized`
— but this is `flyctl launch`'s *own* secondary step of minting a
scoped deploy token for CI use, not a requirement for the app itself; the
app was already created successfully by the time that error printed, and
`flyctl deploy` (which doesn't need that sub-permission) worked normally
right after.

## 2026-07-14 — `flyctl deploy` defaults to 2 machines (HA), not 1

**What happened:** the redeploy above (`flyctl deploy` against a
newly-created app with no existing machines) provisioned **two** machines
for high availability by default, even though `flyctl launch` had been run
with `--ha=false`. That flag only affects `launch`, not a later plain
`deploy` against an app with no machines yet — `deploy` has its own
default of creating a second machine for zero-downtime deploys.

**Why it matters here specifically:** the rate limiter
(`src/api/rate_limit.py`) is an in-memory, per-process, per-machine
counter — a deliberate choice documented in `ROADMAP.md` and
`docs/deployment.md` *because* this deployment is a single machine. Two
machines silently doubles the effective rate limit (each machine tracks its
own count; Fly's proxy can route consecutive requests to either one) — not
a security hole, but a real drift from the documented architecture that
would go unnoticed without checking `flyctl status`.

**Fix:** `flyctl scale count 1 -a ncm-classifier-ai` (after explicit
confirmation — this is a production infrastructure change and Claude
Code's own permission classifier correctly refused to run it
unprompted). Both machines auto-stop when idle either way, so the actual
cost difference is close to zero — this was about matching the documented
single-machine architecture, not saving money.

**Takeaway:** after any `flyctl deploy` that creates machines from scratch
(new app, or scaled to zero and back), check `flyctl status -a
<app>` and confirm the machine count matches what the architecture
assumes, rather than trusting `fly.toml`/CLI flags from a *previous*
command to still apply.

**Current state: live.** `https://ncm-classifier-ai.fly.dev` (v0.2.0), one
machine in `gru`, confirmed end-to-end: `/health`, `/`, `/docs`, `/classify`
(both without a credential and with an invalid `X-LLM-Api-Key`, returning
a clean `422`), and security headers all verified against the real
deployment.

## 2026-07-15 — Fly.io trial ended, app unreachable (billing, not config)

**What happened:** the deployment above went unreachable a day later.
`flyctl status -a ncm-classifier-ai` returns
`Error: failed to list active VMs: trial has ended, please add a credit
card by visiting https://fly.io/trial` — confirmed by `GET /health` also
timing out against the public URL. No config or code issue: `fly.toml`/
`Dockerfile` are unchanged and were working correctly right up to this
point.

**Diagnosis:** Fly.io's free trial period expired on the account. Unlike
the earlier `unauthorized` app-creation block (a separate, already-resolved
issue), this one explicitly names the fix: add a payment method at
[fly.io/trial](https://fly.io/trial) (or the dashboard's Billing page).
This is account/billing access only the maintainer has — entering payment
details isn't something to automate here.

**Current state: down**, pending the maintainer adding a payment method.
No redeploy or config change is needed once billing is sorted — the
existing app should resume; if it doesn't, fall back to the recreate flow
already documented above (`flyctl launch --copy-config --yes --org
personal --name ncm-classifier-ai --region gru --no-deploy --ha=false`
then `flyctl deploy`, then `flyctl scale count 1`).

**Takeaway:** a portfolio deployment on any pay-as-you-go platform's free
tier carries this exact risk — trial/free-tier limits can lapse
independently of anything in the repo. README/STATUS.md now describe the
deployment without an unconditional "it's live" claim, precisely so a
lapse like this doesn't leave the docs asserting something false to a
visitor who clicks through.
