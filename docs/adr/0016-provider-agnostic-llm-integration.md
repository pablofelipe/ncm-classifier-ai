# ADR-0016 — Provider-Agnostic LLM Integration

**Status:** Accepted — ships
**Date:** 2026-07-13
**Deciders:** Pablo Felipe

---

## Context

### Why this isn't "add Gemini support" — it already had that

ADR-0013 shipped Gemini 2.5 Flash rerank, reaching the project's flagship
result (71.7% top-1 / 75.7% top-3 on the v2 corpus). That path worked and
needed no fixing on its own merits. What changed is the project's next goal,
decided in ADR-0015: turning `ncm-classifier-ai` from a project that only
runs locally into a system with a public URL, so the pipeline can be
exercised live by anyone — not just read about in the README and the
decision log.

### The problem publishing the API actually introduces

`GeminiRerankAdapter` (ADR-0013) read `GEMINI_API_KEY` from `Settings`, i.e.
the maintainer's own credential. Publishing the API with that adapter
unchanged means **every visitor's traffic spends the maintainer's own Gemini
budget**. Hiding the key in a Fly.io/Railway secret does not fix this — the
key would still be reachable by every request the public endpoint serves.
That is not an acceptable posture for a public portfolio deployment.

The fix has to be architectural: the server must be able to run the LLM
rerank path **with no LLM credential of its own**, and a visitor who wants to
see that path live must be able to supply their own credential, scoped to
their own request only.

### The secondary goal this unlocks

Solving the above the right way — a generic `generate()` capability behind
`LLMRerankPort`, rather than a Gemini-shaped one — also removes the project's
only remaining vendor lock-in. The domain already knew nothing about Gemini
(`LLMRerankPort` never named it); `GeminiRerankAdapter` itself, however, mixed
prompt-building/parsing logic with the `google-genai` SDK call in one class.
Splitting those means OpenAI, Anthropic, or DeepSeek become one new adapter
class and one dict entry away, not a parallel reimplementation of the rerank
logic.

---

## Decision

### Components

```
LLMRerankPort (core/ports.py — UNCHANGED)
        ↑ implements
GenericLLMRerankAdapter (src/llm/generic_llm_rerank_adapter.py)
        │  prompt-building, JSON parsing/reordering, fallback — vendor-neutral
        ↓ depends on
LLMClient (src/llm/llm_client.py — Protocol)
        │  generate(model, system_instruction, prompt, response_format) -> str
        ↓ implements
GeminiClient (src/llm/gemini_client.py)
        │  the only concrete LLMClient today; wraps google-genai
```

- **`LLMClient`** is a `Protocol` (not `@runtime_checkable`, matching
  `EmbeddingFunction`'s precedent in `src/retrieval/embedding.py`) — an
  adapter-internal capability contract, not a `core/ports.py` port. The
  domain never touches it; only `GenericLLMRerankAdapter` does.
- **`GenericLLMRerankAdapter(client: LLMClient, *, model: str)`** carries the
  `_TOP_K`/`_SYSTEM`/`_build_prompt` logic moved verbatim from
  `GeminiRerankAdapter` — the PT-BR fiscal prompt was already vendor-neutral,
  nothing Gemini-specific to strip. It no longer knows about
  `ConfigurationError`: credential handling is fully encapsulated inside
  whichever `LLMClient` is injected.
- **`GeminiClient(api_key: str | None = None, client: genai.Client | None = None)`**
  implements `LLMClient`. An explicit `api_key` builds its own
  `genai.Client`, ignoring `settings.gemini_api_key` entirely — this is the
  per-request "bring your own credential" path. With no `api_key` and no
  injected `client`, it falls back to `settings.gemini_api_key` (the
  maintainer's own key, for local dev / CI / server-side default rerank).
- **`resolve_llm_client(provider: str, api_key: str | None = None) -> LLMClient`**
  (`src/llm/llm_client.py`) is a dict-keyed factory
  (`_PROVIDERS = {"google": GeminiClient}`), mirroring
  `make_embedding_function`'s existing pattern in `embedding.py`. Unknown
  provider → `ValueError(f"unknown LLM provider: {provider!r}")`, the same
  idiom `make_embedding_function` already uses for an unknown embedder.
- **`Settings.llm_provider: str = "google"` / `llm_model: str = "gemini-2.5-flash"`**
  replace the Gemini-specific `gemini_flash_model`. Deliberately **plain
  `str`, not `StrEnum`** — unlike `RerankMode`/`RetrievalMode`/`EmbedderModel`,
  which gate a fixed `if`/`elif` in `dependencies.py`, `LLM_PROVIDER` is meant
  to stay open: a new provider is a dict entry in `resolve_llm_client`, never
  an edit to `Settings` or the composition root's branching.
  `gemini_api_key` keeps its Gemini-specific name on purpose — it documents
  that it is *not* the extensible mechanism, only the maintainer's own
  local/CI/server-side credential.

### Per-request credential override

`ClassifyProduct` (constructor and `execute()`) and `LLMRerankPort` are
**completely unchanged** by this ADR. Instead:

- `build_classify_use_case()` — already the pure, FastAPI-free composition
  function shared by the HTTP dependency and `eval/run_eval.py` — gained one
  keyword-only parameter: `rerank_override: LLMRerankPort | None = None`.
  When given, it supersedes whatever `settings.rerank_mode` would have
  selected, including `PASSTHROUGH`.
- `get_classify_use_case()` (the FastAPI wrapper) reads three optional
  headers — `X-LLM-Api-Key`, `LLM-Provider`, `LLM-Model` — via
  `Header(default=None, alias=...)`, and builds the override through a new
  pure helper, `_resolve_rerank_override`:

  ```python
  def _resolve_rerank_override(
      x_llm_api_key, llm_provider=None, llm_model=None,
  ) -> LLMRerankPort | None:
      if not x_llm_api_key:
          return None
      provider = llm_provider or settings.llm_provider
      model = llm_model or settings.llm_model
      try:
          client = resolve_llm_client(provider, api_key=x_llm_api_key)
      except ValueError as exc:
          raise HTTPException(status_code=422, detail=str(exc)) from exc
      return GenericLLMRerankAdapter(client, model=model)
  ```

- **`LLM-Provider`/`LLM-Model` are only ever consulted inside the
  `x_llm_api_key` branch.** Sending them alone, without a key, can never
  trigger a call on the server's own credentials — there might not even be
  one. This is the concrete mechanism that makes "the public deployment
  carries no server-side LLM key" an enforceable property, not just a
  configuration choice that a future change could quietly undo.
- The key exists only in that one call's stack frame: it flows straight into
  a freshly constructed `GenericLLMRerankAdapter`/`GeminiClient` and is never
  assigned to `settings`, a module global, or any cache. `src/api/routes.py`
  needed **no changes** — `Depends(get_classify_use_case)` already forwards
  request headers to whatever `Header()` parameters the dependency declares.

### Cutover

`RerankMode.GEMINI` now wires `GenericLLMRerankAdapter(resolve_llm_client(settings.llm_provider), model=settings.llm_model)`
in `dependencies.py`, replacing `GeminiRerankAdapter()`. At that cutover,
`src/llm/gemini_rerank_adapter.py` and its test file were deleted outright,
along with the dead `rank_candidates()` stub and `_client()` free function in
`gemini_client.py` (absorbed inline into `GeminiClient._get_client()`), and
`gemini_flash_model`/`gemini_pro_model` from `Settings` (`gemini_pro_model`
was already unused before this ADR). No compatibility shim was kept — once
the replacement's parity was confirmed, the old path was dead code, and this
project's convention is to delete dead code rather than let it linger "just
in case."

---

## Alternatives Considered

**Per-request override shape.** Two designs were on the table before this
one:
- **(a) An `execute()`-time parameter on `ClassifyProduct`** —
  `execute(query, rerank_override=...)`. Rejected: it would touch the use
  case's public contract for a concern (per-request credential plumbing)
  that has nothing to do with classification logic, and every existing
  caller of `execute()` would need to reason about a new parameter it never
  uses.
- **(b) A whole fresh `ClassifyProduct` built per request** when an override
  is needed, re-deriving retrieval/verification wiring in a second code
  path. Rejected as unnecessary duplication: there is already exactly one
  composition function (`build_classify_use_case`); parameterizing it is
  strictly simpler than maintaining two.
- **(Chosen) A keyword-only `rerank_override` on `build_classify_use_case`**,
  resolved from headers only in the thin FastAPI wrapper. Every port
  (`RetrievalPort`, `LLMRerankPort`) and every use-case signature
  (`ClassifyProduct.__init__`/`execute()`) stays byte-for-byte unchanged;
  `eval/run_eval.py`'s `Callable[[], ClassifyProduct]` typing of
  `build_classify_use_case` still holds, since the new parameter is optional
  and keyword-only.

**Module layout: flat `src/llm/` vs a `providers/` subpackage.** With only
one real provider (`GeminiClient`) implemented, a `src/llm/providers/`
subpackage was rejected as speculative structure — the same bias this
project already demonstrated in ADR-0007 (closing the enrichment line rather
than building more configurability for an unproven lever) and ADR-0012
(rejecting the cross-encoder rather than keeping it as a maybe-someday
option). `LLMClient` + `resolve_llm_client` live together in
`llm_client.py` (mirroring `EmbeddingFunction` + `make_embedding_function` in
`embedding.py`); `GeminiClient` keeps its own file, matching the existing
one-adapter-per-file convention (`gemini_rerank_adapter.py`,
`cross_encoder_adapter.py`, `passthrough_adapter.py` before it). Promoting to
a `providers/` subpackage is the natural move *when* a second provider is
actually added — not before.

**`llm_provider` as `str` vs `StrEnum`.** Rejected `StrEnum` (the pattern
`RerankMode`/`RetrievalMode`/`EmbedderModel` all use) specifically because
those three enums each gate a fixed `if`/`elif` chain that must be edited to
add a value. `LLM_PROVIDER` is meant to grow via `resolve_llm_client`'s dict
without touching `Settings`, `dependencies.py`, or `core/` at all — an enum
would work against that goal by reintroducing an edit point.

---

## Measured Delta

The intended gate was a full 350-case `make eval-gemini-rerank` run before
and after the cutover, confirming identical **71.7% top-1 / 75.7% top-3**
(the ADR-0013 numbers). In practice, the Gemini API was unstable during this
measurement window: a first full-350 attempt crashed with
`google.genai.errors.ServerError: 503 UNAVAILABLE` after `tenacity` exhausted
its retries (on the pre-cutover code — confirming the instability was
external, not a regression); a second attempt, post-cutover, ran far past its
expected ~12-minute wall time without completing.

Rather than keep re-running the full suite against an unstable upstream, the
gate was substituted with a **30-case stratified sample** (5 cases per
`mode`: direct, colloquial, poverty, negation, frontier, multi_attr), run
**before** the cutover (temporarily via `git stash`, restoring
`GeminiRerankAdapter`) and **after** (current code), on the same cases:

| | Top-1 | Top-3 | Per-difficulty | Per-mode |
|---|---|---|---|---|
| Before (`GeminiRerankAdapter`) | 18/30 = 60.0% | 20/30 = 66.7% | identical | identical |
| After (`GenericLLMRerankAdapter`) | 18/30 = 60.0% | 20/30 = 66.7% | identical | identical |

Every breakdown matched exactly — strong evidence of behavioral parity,
though on a smaller sample than the full 350-case corpus. **A full-350
confirmation run is still open**, deferred to whenever the Gemini API is
stable enough to complete it; it is not expected to change the conclusion,
since the code paths differ only in which object issues an identical
`generate_content` call with an identical prompt.

Manual smoke tests against a live `uvicorn` instance additionally confirmed,
without spending any real LLM budget: no header → 200, Passthrough, no cost;
invalid `X-LLM-Api-Key` → the request reaches a real (rejected) Gemini call
("API key not valid"), proving the header wiring is live, at zero token
cost; unknown `LLM-Provider` → `422` with a clear message; `LLM-Provider`/
`LLM-Model` sent alone, without a key → identical output to the no-header
case, confirming they never trigger a call on their own.

---

## Consequences

- **Deleted**: `src/llm/gemini_rerank_adapter.py` and its test file;
  `gemini_client.rank_candidates()` (the ADR-0013-era stub, never called) and
  its module-level `_client()` helper (absorbed into
  `GeminiClient._get_client()`); `Settings.gemini_flash_model` and the
  already-unused `Settings.gemini_pro_model`.
- **New extension point**: adding OpenAI, Anthropic, or DeepSeek support is
  one new `LLMClient` implementation plus one `_PROVIDERS` dict entry in
  `resolve_llm_client` — no change to `core/`, `ClassifyProduct`, or
  `dependencies.py`'s branching logic.
- **Production posture, by construction, not by convention**: the public
  deployment can set no `GEMINI_API_KEY` at all and still serve `/classify`
  (Passthrough or hybrid retrieval, zero LLM cost per request). A visitor who
  wants the LLM-rerank path supplies their own key via `X-LLM-Api-Key`,
  scoped to that one request, never persisted/logged/cached. `LLM-Provider`/
  `LLM-Model` sent without a key are inert by construction (see `Measured
  Delta` smoke tests) — this is enforced by where the code reads the
  headers, not by a policy someone has to remember to keep respecting.
  Application-level rate limiting is still recommended before the URL goes
  public, to bound compute/hosting cost even though there is no LLM budget to
  protect on the default path — tracked as a separate concern (Fase 3/4 of
  the public-deployment roadmap), out of scope here.
- **Known gap, flagged separately**: a provider API error (e.g. an invalid
  visitor-supplied key) currently surfaces as an unhandled `500` with a full
  stack trace — pre-existing behavior inherited from `GeminiRerankAdapter`,
  not introduced by this ADR, but worth closing before the public deployment
  ships (mapping provider `APIError`s to a clean `4xx`/`502` without leaking
  internals).
- **Accepted technical debt, naming**: `RerankMode.GEMINI` keeps its
  original enum name even though the mechanism it now selects is fully
  generic — it resolves whatever `LLM_PROVIDER` is configured, not
  necessarily Gemini. Renaming it (e.g. to `RerankMode.LLM`, mirroring the
  `LLM_PROVIDER`/`LLM_MODEL` rename this ADR already made) would be a
  breaking `RERANK_MODE` config change on top of the ones already shipped
  here; deferred rather than compounding two breaking renames in one ADR.
  Revisit when a second provider is actually added — the naming gap will
  be more conspicuous once `RERANK_MODE=gemini` can select something that
  isn't Gemini.
- **Full-350 eval-parity confirmation** is open, deferred by external API
  instability during this ADR's measurement window (see `Measured Delta`).
- **Path forward**: Fase 1 (Docker/Fly.io deterministic deploy, baked Chroma
  index) and Fase 4 (actual public deployment) remain future work, each
  meriting its own planning pass — this ADR only covers making the LLM
  integration safe to expose, not the deployment mechanics themselves.
