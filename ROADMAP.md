# Roadmap

This is an architectural roadmap, organized by pillar — not a chronological
TODO list. Each row states what's still open and why it matters; the
reasoning behind decisions already made lives in the ADR it links to, not
here. Finished work lives in [STATUS.md](STATUS.md), not in this file — an
item disappears from here once it ships.

**Priority:** P0 blocks the next milestone (a public deployment) · P1 matters
soon after that milestone · P2 improves the system but isn't blocking
anything · P3 low-effort housekeeping.

## Architecture

| Priority | Status | Item | Reference |
|---|---|---|---|
| P2 | Planned | Formalize `resolve_llm_client`'s provider dict into an explicit registry, decoupled from the hardcoded `_PROVIDERS` module constant | — |
| P3 | Planned | Introduce structured `LLMRequest`/`LLMResponse` types in place of `LLMClient.generate()`'s raw `str` return | — |
| P3 | Planned | Resolve the `poetry.lock` / `hatchling` build-backend mismatch (likely a leftover artifact from before the build system settled) | — |

## Deployment

| Priority | Status | Item | Reference |
|---|---|---|---|
| P2 | Planned | Distributed rate limiting (Redis-backed) if the deployment ever grows beyond a single Fly.io machine — today's in-memory per-process limiter (Etapa 7) is a deliberate, scoped choice, not a placeholder | — |
| P3 | Planned | `flyctl deploy` defaults to 2 machines on a from-scratch app (HA), not 1 — scaled down manually after the first real deploy; worth double-checking machine count after any future from-scratch redeploy rather than assuming `fly.toml`/CLI flags carry over | `docs/operational-notes.md` |
| P3 | Planned | Reduce cold-start latency (~15s one-time per process, see `docs/operational-notes.md`) if real traffic makes it matter — no decision made yet on warm-up requests vs. `min_machines_running=1` | — |
| P3 | Planned | Tune Fly.io VM size (`shared-cpu-2x`/2GB in `fly.toml` is a starting guess, not measured) once there's real traffic | — |

## Retrieval

| Priority | Status | Item | Reference |
|---|---|---|---|
| P2 | Planned | Expand the corpus beyond the beverage domain (Ch.20/21/22) to test generalization | ADR-0013, CLAUDE.md path forward |

## LLM

| Priority | Status | Item | Reference |
|---|---|---|---|
| P2 | Planned | Rename `RerankMode.GEMINI` to a provider-neutral name, once a second `LLM_PROVIDER` actually exists | ADR-0016 (accepted debt) |
| P2 | Planned | Confirm full 350-case parity for the ADR-0016 cutover — only a 30-case stratified sample is confirmed so far. **Requires a real Gemini API run; needs explicit approval before executing** | ADR-0016 (Measured Delta) |

## Verification

| Priority | Status | Item | Reference |
|---|---|---|---|
| P3 | Planned | Revisit demoting a verification-failed top candidate below a lower-ranked passing one — explicitly out of scope when the gate was wired | ADR-0014 |

## Evaluation

| Priority | Status | Item | Reference |
|---|---|---|---|
| P2 | Planned | Extend the eval dataset to a second product domain, alongside the corpus expansion above | ADR-0009, CLAUDE.md path forward |
| P2 | Planned | Calibrate confidence scores — ECE is currently unmeasured/uncalibrated; Gemini's ranking order drives top-3 selection today, but the scores it emits aren't probabilities | ADR-0004, ADR-0009, ADR-0013, CLAUDE.md path forward |

## Observability

| Priority | Status | Item | Reference |
|---|---|---|---|
| P2 | Planned | Structured logging — none exists today beyond `escalation_reason` surfaced in the API response | — |
| P2 | Planned | Per-provider usage and latency metrics | — |

## Performance

No open items identified from the current ADRs or codebase. The pillar stays
in the taxonomy for when real deployment traffic surfaces a bottleneck worth
measuring — nothing is listed here speculatively.

## Documentation

No open items. This pillar's baseline (a roadmap, a status snapshot and a
deployment runbook, each with a single responsibility) is what this change
establishes — see [STATUS.md](STATUS.md) for confirmation. Future items here
would be triggered by new artifacts becoming necessary (e.g. an API
reference, a contributing guide), not listed speculatively now.

## See also

- [STATUS.md](STATUS.md) — what's actually built, right now.
- [docs/deployment.md](docs/deployment.md) — how to run and publish it.
- [docs/adr/](docs/adr/) — why each decision was made.
