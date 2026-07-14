# ADR-0015 — Public Deployment Architecture

**Status:** Accepted — decision only, deploy not yet executed
**Date:** 2026-07-13
**Deciders:** Pablo Felipe

---

## Context

The project has reached enough maturity in architecture, experimentation, and
evaluation discipline that its remaining gap is no longer methodological —
it's exposure. Fourteen ADRs document a hexagonal RAG pipeline, evidence-based
retrieval/rerank decisions, and an eval-first discipline, but the system can
still only be run locally. A collaborator can read the README, study the
decision log, and see the metrics table, but cannot send a product
description and watch the pipeline classify it live. A public URL where the
pipeline can be exercised directly is worth more than any static metrics
table — this is the last piece of maturity the project is missing.

`CLAUDE.md` already names Fly.io (or Railway) as the deploy target, but that
step was never executed. This ADR is the decision that turns "deploy target"
from a stated intention into an architecture.

Publishing the API changes the requirements entirely. Concerns that don't
exist for a local-only research project become load-bearing:

- deterministic, reproducible deploys
- ongoing operation (not a one-time `make run`)
- operational cost
- security and abuse surface
- environment configuration
- the deployment's own financial sustainability

## Problem

The most consequential of these is the last one, and it isn't abstract: a
public API running with the maintainer's own `GEMINI_API_KEY` would let any
visitor consume credits paid for by the project's owner. There is no rate
limit, authentication, or usage cap that makes this acceptable on its own —
the exposure is the credential's mere presence on a publicly reachable
server. This model is incompatible with a public, open-source portfolio
project: the whole point is that anyone can try it, which is exactly the
population a shared credential can't be exposed to.

Everything else in this ADR — Docker, Fly.io, baked indexes, scale-to-zero —
is ordinary deployment engineering. This one problem is the reason the
deployment has to be *designed*, not just executed.

## Alternatives Considered

- **Stay local-only.** Rejected: this is the status quo the ADR exists to
  change. It preserves zero cost and zero exposure but caps the project's
  value to what's readable in a README — the stated goal is a live,
  triable system.
- **Fly.io.** Accepted as the target platform. Supports Docker-based
  deploys, per-machine scale-to-zero with fast wake, and volumes if ever
  needed — matches this project's Docker-first, config-over-infrastructure
  style better than a buildpack-driven platform would.
- **Railway.** Considered as an alternative to Fly.io. Not rejected
  outright — kept as a fallback if a concrete technical reason surfaces
  during the actual deploy (Fase 4) to prefer it. No such reason exists
  yet, so Fly.io is the default rather than a other-things-being-equal
  coin flip.
- **Persistent volume for the Chroma index.** Rejected for this project's
  scale. The corpus is small (64 NCMs for the beverage config) and static
  between deploys; a volume adds an operational dependency (attach/mount,
  backup, drift between volume contents and the code that reads them) for
  no benefit a baked-in index doesn't already provide.
- **Bake the Chroma index into the Docker image.** Accepted. The index is
  fully reproducible from `data/tipi/*.json` at build time
  (`make index`/`make index-v2`), so baking it in makes the image the unit
  of deployment and rollback: a given image tag is a fully self-contained,
  reproducible snapshot of code *and* data. The trade-off — a corpus update
  requires an image rebuild rather than a live data push — is acceptable
  for a corpus that changes on the order of ADRs, not requests.
- **Store the Gemini key as a Fly.io/Railway secret.** Rejected as the
  *complete* answer, though not because secrets are unsafe — because a
  secret still makes the key reachable by every request the public
  endpoint serves. Hiding the credential in a secrets manager solves
  "who can read the key's value" (an infra concern) but not "who can spend
  the key's budget" (an architectural one). Those are different problems;
  this ADR is about the second one.
- **Require the client to supply their own credential.** Accepted as the
  actual answer to the problem above. The server holds no LLM credential
  of its own for public traffic; a visitor who wants the LLM-rerank path
  brings their own key, scoped to their own request. The mechanics of this
  (which headers, how the credential flows through the pipeline, how it's
  guaranteed to never be logged or cached) are an implementation concern
  deferred to ADR-0016 — this ADR only fixes the requirement: *the public
  deployment must be able to run with no server-side LLM key at all.*

## Decision

The project will be prepared for public deployment under these constraints:

- The Chroma index is baked into the Docker image at build time — no
  persistent volume, no runtime index-build step. A deploy is a build.
- The deployment must operate at near-zero recurring cost. This follows
  from two things this ADR fixes and one it doesn't: no LLM key on the
  server (fixed here, mechanics in ADR-0016) means zero LLM spend on the
  default path; scale-to-zero (below) means zero compute spend while idle.
  Rate limiting to bound raw compute/hosting abuse is real but is an API
  Hardening concern (Fase 3), not fixed by this decision.
- The deployment must support scale-to-zero — the instance suspends when
  idle and wakes on request, so a demo with sparse, intermittent traffic
  costs close to nothing while unused.
- **The public server will hold no credential of its own for LLM
  consumption.** This is the architectural constraint this ADR exists to
  state; ADR-0016 is where it's actually implemented (provider-agnostic
  `LLMClient` + per-request `X-LLM-Api-Key`).
- Public API hardening beyond "no server-side LLM key" — rate limiting,
  input validation against abuse, credential-header ergonomics — is
  explicitly deferred to the ADRs that follow (ADR-0016 and a future
  Public API Hardening decision), not bundled into this one.

## Consequences

**Positive:**
- Reproducible deploys: a Docker image tag is the entire unit of release —
  code and data together, nothing to drift between them.
- Simple rollback: redeploying a prior image tag is the entire rollback
  procedure, no data migration to reverse.
- No persistent-storage dependency for the vector index — one less moving
  part to operate, back up, or lose sync with the code.
- Low operational cost by construction (scale-to-zero + no default LLM
  spend), not by a policy someone has to remember to enforce.
- The architecture is now shaped for public operation, not just local
  experimentation — the remaining deploy work (Fase 4) is mechanical.

**Trade-offs:**
- A corpus update (new TIPI data, new synonyms) requires an image rebuild
  and redeploy, not a live data push. Acceptable at this project's update
  cadence.
- The deploy flow (build → bake index → push image → deploy) needs to be
  documented clearly enough that it's repeatable without re-deriving it
  from scratch each time (Fase 4 work).
- This decision alone doesn't finish the job: it requires ADR-0016
  (provider-agnostic LLM integration, no server-side credential) and a
  future Public API Hardening ADR (rate limiting, credential ergonomics)
  before the deployment is actually safe to make public.
- **Operational risk, flagged for the deploy that executes this ADR (Fase
  4), not solved by it:** ADR-0016's per-request `X-LLM-Api-Key` guarantees
  the *application* never logs, caches, or persists a visitor's credential.
  It does not, by itself, guarantee that *infrastructure* around the
  application — a reverse proxy, an access-log pipeline, an APM/tracing
  tool — won't capture that header by default, since many such tools log
  request headers indiscriminately unless configured otherwise. Whoever
  executes the deploy must explicitly configure the hosting platform's
  logging/tracing to redact `X-LLM-Api-Key` (and any future per-request
  credential header), rather than assume the application-level guarantee
  is sufficient end to end.

## Relation to ADR-0016

This decision is the reason ADR-0016 exists, not a parallel, independently
motivated one. The provider-agnostic `LLMClient`/`GenericLLMRerankAdapter`
abstraction wasn't pursued for its own sake — decoupling from Gemini would
have been a reasonable refactor on its own merits, but it wasn't what
*triggered* the work. What triggered it was this ADR's constraint that the
public server must hold no LLM credential of its own: once that constraint
is fixed, "how does a request still get LLM rerank" necessarily requires a
per-request credential mechanism, and building that mechanism cleanly is
what made the vendor-agnostic abstraction the right shape rather than a
Gemini-specific header hack. ADR-0016 documents the *how*; this ADR
documents the *why it had to be solved at all*.
