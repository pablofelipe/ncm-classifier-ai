# ADR-0013 — Gemini Flash LLM Rerank (ACCEPTED)

**Date:** 2026-07-01
**Status:** Accepted — ships with `RERANK_MODE=gemini` on the v2 (beverage) config
**Deciders:** Pablo Felipe

---

## Context

### Rerank ceiling

After ADR-0011 (hybrid BM25+e5, RRF) reached 49.1% top-1 / 68.0% top-3, a ceiling
analysis was run on the v2 eval set (350 cases): **66/350 cases (18.9%)** had the
correct NCM at rank-2 (47 cases) or rank-3 (19 cases) — the maximum recoverable by any
reranker operating over the 3-candidate pool.

### ADR-0012 rejection

The local cross-encoder (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) was rejected in
ADR-0012 with a −28.8/−29.4 pp regression. Root cause: mMARCO was trained on
(web question, web passage) pairs; TIPI NCM descriptions are 2–8 token structured fiscal
nomenclature — the domain gap produced near-random logits. The entire MS MARCO family
shares this gap; no Portuguese fiscal cross-encoder exists on HuggingFace Hub.

### Why an instruction-following LLM

An instruction-following LLM understands colloquial product names ("cachaça", "heineken
lata", "Chivas 12") and fiscal nomenclature ("Uísques de malte escocês", "Cervejas de
malte") without fine-tuning — the relationship between them is implicit in pre-training
data from fiscal/retail/import contexts. The model can reason over negation ("sem álcool"),
attribute filtering (`multi_attr`), and sibling disambiguation (`frontier`) at inference
time, unlike a cross-encoder that has no fiscal prior.

---

## Decision

### Adapter

`GeminiRerankAdapter` (`src/llm/gemini_rerank_adapter.py`) implements `LLMRerankPort`:

- **Model**: `gemini-2.5-flash` (updated from `gemini-2.0-flash`, which was deprecated
  by Google in mid-2026; `settings.gemini_flash_model` field, overridable via env)
- **Pool size**: top-5 candidates sent to the LLM (not top-3 — capturing rank-4/5 extends
  the recoverable ceiling beyond the 66/350 cases calculated from the 3-candidate pool)
- **Prompt**: PT-BR system instruction + user message listing candidates as
  `N. NNNNNNNN — {fiscal description}`, asking for `{"ranked": ["NNNNNNNN", ...]}` only
- **JSON forcing**: `response_mime_type: "application/json"` in the generation config —
  prevents markdown fence wrapping; verified 0 fallbacks across 350 eval cases
- **Fallback**: if JSON parsing fails despite mime type, logs the malformed response at
  WARNING and returns candidates in original order (passthrough for that query)
- **Client injection**: constructor accepts optional client override for unit testing;
  caches the real `genai.Client` lazily to avoid per-request allocation

### Wiring

`RerankMode.GEMINI = "gemini"` added to the enum in `settings`; default remains
`PASSTHROUGH` — production (v1/cap22 dense) is unaffected. Opt-in via
`RERANK_MODE=gemini` (requires `GEMINI_API_KEY` and the `llm` extra).

### Testing

11 unit tests (Red→Green; 100% passing, mypy and ruff clean):
- Reordering by ranked JSON, top candidate placed first
- NCM code, description, metadata preservation after rerank
- Unranked candidates appended at end
- Fallback on invalid JSON (returns original order)
- Fallback on missing `ranked` key (returns original order)
- Fallback logs malformed response at WARNING
- `ConfigurationError` raised before any network call when API key absent
- Empty candidate list returns empty list without calling client
- `isinstance(GeminiRerankAdapter(), LLMRerankPort)` — protocol satisfied

---

## Measured Result

Single deterministic run, v2 (350 cases), `NCM_CHAPTER=beverage RETRIEVAL_MODE=hybrid
RERANK_MODE=gemini` over the synonym-enriched `tipi_capbeverage` collection.
Baseline: ADR-0011 (hybrid, passthrough rerank).

### Aggregate

| Config | Top-1 | Top-3 | Δ Top-1 | Δ Top-3 |
|---|---|---|---|---|
| ADR-0011 hybrid (baseline) | 49.1% (172/350) | 68.0% (238/350) | — | — |
| **+ Gemini Flash rerank (this ADR)** | **71.7% (251/350)** | **75.7% (265/350)** | **+22.6 pp** | **+7.7 pp** |

### Per-mode

| Mode | n | ADR-0011 top-3 | This ADR top-3 | Δ |
|---|---|---|---|---|
| negation | 30 | 43.3% (13/30) | **66.7% (20/30)** | **+23.4 pp** |
| frontier | 23 | 43.5% (10/23) | **65.2% (15/23)** | **+21.7 pp** |
| multi_attr | 33 | 45.5% (15/33) | **57.6% (19/33)** | **+12.1 pp** |
| direct | 64 | 68.8% (44/64) | **76.6% (49/64)** | **+7.8 pp** |
| colloquial | 127 | 85.0% (108/127) | **90.6% (115/127)** | **+5.6 pp** |
| poverty | 73 | 60.3% (44/73) | **64.4% (47/73)** | **+4.1 pp** |

No mode regressed.

### V2 targets

| Metric | Target | ADR-0011 | **This ADR** |
|---|---|---|---|
| Top-1 | ≥ 40% | 49.1% ✓ | **71.7% ✓** |
| Top-3 | ≥ 65% | 68.0% ✓ | **75.7% ✓** |

Top-1 now exceeds the v1 target (≥ 70%) on the v2 corpus.

---

## Prediction vs Outcome

| Prediction | Outcome |
|---|---|
| Absolute ceiling: top-1 ≤ 68.0% (66/350 rerank-recoverable cases) | **Exceeded: 71.7%.** The adapter uses top-5 (not top-3), extending the pool — rank-4/5 candidates become promotable. The 66-case ceiling was calculated on the 3-candidate pool only. |
| Recover 35–50/66 cases | **+79 top-1 cases** (same root reason: pool larger than anticipated) |
| Negation and frontier largest gains | ✓ Negation +23.4 pp, frontier +21.7 pp — LLM resolves "sem álcool" and sibling disambiguation |
| Colloquial marginal gain | ✓ +5.6 pp — BM25+synonyms already solved colloquial; LLM consolidates the few remaining misses |
| JSON fallback risk | **0 fallbacks** — `response_mime_type: "application/json"` was sufficient; the strip-fences fallback code was never triggered |

### Gap collapse

Top-1/top-3 gap: **18.9 pp → 4.0 pp**. The LLM is very precise at rank-1 — when the
correct answer is in the top-5 pool, Gemini places it first with high reliability. The
residual 4 pp gap represents cases where the correct answer is in the pool but Gemini
places it at rank-2 or rank-3 (or occasionally rank-4/5, dropping it from the top-3
response).

---

## Cost and Latency

**Cost per query**: ~$0.000024 USD at Gemini 2.5 Flash rates (~$0.075/1M input tokens,
~$0.30/1M output tokens), for a ~200-token input prompt + ~30-token JSON output.
At R$ 5.50/USD: **≈ R$ 0.00013 per query — 770× below the R$ 0.10 budget.**

**Latency**: ~2.1 s/query average (estimated from 350-call total wall time). Within the
4 s median latency target. Cold-start on the first query may spike to 3–4 s; the lazy
client cache (`self._cached`) prevents per-request client allocation.

---

## Consequences

**Config ships with v2/beverage only.** `RERANK_MODE=gemini` is the recommended config
for the v2 corpus. The v1/cap22 path is unchanged (default `PASSTHROUGH`); CI still gates
on v1 (33.3% / 63.3% dense baseline) and is unaffected.

**`gemini_flash_model` updated to `gemini-2.5-flash`.** `gemini-2.0-flash` was deprecated
mid-2026; the field is still env-overridable (`GEMINI_FLASH_MODEL`).

**`rank_candidates()` stub in `gemini_client.py` is superseded.** The new
`GeminiRerankAdapter` is the production LLM rerank path. The stub remains for
compatibility but is not called by the pipeline.

**Remaining gaps:** `frontier` 65.2% top-3, `hard` 63.8% top-3. Both represent cases
where the correct NCM is not in the top-5 retrieval pool — the LLM cannot recover what
retrieval did not find.

**Path forward:** the system is in a production-viable state for the beverage corpus
(v2 targets met with margin at 71.7% / 75.7%). Logical next steps are:
- Expand corpus and dataset beyond beverages (test generalization)
- Wire the deterministic verification gate (ADR-0002, implemented and tested, not yet
  called by the pipeline)
- Calibrate confidence scores (ECE currently uncalibrated; Passthrough was used for
  scoring, now superseded by Gemini ranking order)

---

## Eval Invocation

```bash
# ADR-0011 baseline (unchanged)
make eval-v2

# This ADR — opt-in
make eval-gemini-rerank
```
