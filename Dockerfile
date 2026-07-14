# syntax=docker/dockerfile:1
#
# Production image (ADR-0015). Generic on purpose — no Fly.io-specific
# configuration lives here; the platform (Fly.io, Cloud Run, ECS, Railway,
# k8s) only needs to run this image and point a health check at GET /health.
#
# Etapa 3: bakes the "Default Public Deployment Profile" — the beverage
# corpus (ADR-0009, Ch.20/21/22), synonyms-enriched (ADR-0010), hybrid
# retrieval (ADR-0011), Passthrough rerank by default (no server-side LLM
# credential — ADR-0015/0016; a caller's own X-LLM-Api-Key still reaches the
# Gemini-rerank path unchanged). Chosen for being deterministic,
# reproducible and zero recurring cost, not for being the single best score
# — a visitor who brings their own key gets the stronger 71.7%/75.7% result
# (ADR-0013) on top of this same baked index.

# ---- builder ----------------------------------------------------------
# Isolated so build-only cost (pip's resolver/cache, any wheel that needs a
# compiler) never reaches the runtime image — only /opt/venv is copied out.
FROM python:3.13-slim AS builder

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# CPU-only torch first, from its dedicated index (see README "Install
# (development)") — otherwise pip's resolver can pull the ~2GB CUDA wheel.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# pyproject.toml + src/ together: hatchling needs the actual source tree
# present to build the wheel (dependencies are declared statically, but the
# build backend still packages real files, not just metadata).
COPY pyproject.toml ./
COPY src ./src

# `ml` + `llm` ship to runtime; `dev` (pytest/ruff/mypy) and `scripts`
# (openpyxl) never do — this image never runs tests, lints, or XLSX ingestion.
# `ml` is required at request time, not just at build time:
# src/retrieval/embedding.py's embed_query() runs on every retrieval call, so
# sentence-transformers/torch are a runtime dependency for every request.
# `llm` (google-genai) is required at request time too, for BYOK (ADR-0016):
# the server's own RERANK_MODE is Passthrough (no LLM), but any visitor who
# sends X-LLM-Api-Key exercises GeminiClient right then, in that container —
# without this extra, that path would fail with ModuleNotFoundError instead
# of the clean LLMProviderError handling Etapa 7 adds.
RUN pip install --no-cache-dir ".[ml,llm]"

# Deterministic cache path, independent of which user/HOME is active — the
# runtime stage's non-root user has no HOME (--no-create-home), so relying
# on the default "~/.cache/huggingface" would break there. Set once, copied
# verbatim into runtime below.
ENV HF_HOME=/opt/hf-cache

# TIPI source (ADR-0009, chapter=beverage) and the ADR-0010 synonyms file —
# both already committed to the repo, no XLSX ingestion needed in this build.
COPY data/tipi ./data/tipi
COPY data/synonyms ./data/synonyms

# Bake the index (ADR-0015: "a deploy is a build", never rebuilt at
# runtime). Downloads the pinned multilingual-e5-small revision into
# HF_HOME — the one point in this whole image where network egress is
# required (see ADR-0015 discussion). NCM_CHAPTER=beverage selects the v2
# corpus; ENRICH_STRATEGY (OFF, the Settings default) plus chapter=beverage
# together mean the ADR-0010 synonyms are applied automatically — no extra
# flag needed, that gating already lives in chroma_client._synonyms_for_chapter.
ENV NCM_CHAPTER=beverage
RUN python -m src.retrieval.chroma_client rebuild

# ---- runtime ------------------------------------------------------------
FROM python:3.13-slim AS runtime

# Fixed UID/GID: deterministic ownership across rebuilds, not a
# shell-assigned "next available" id that could drift between builds.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --shell /usr/sbin/nologin app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HF_HOME=/opt/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    NCM_CHAPTER=beverage \
    RETRIEVAL_MODE=hybrid \
    RERANK_MODE=passthrough

WORKDIR /app

# WORKDIR creates /app as root; chown it so the non-root user can create
# settings.chroma_path ("data/chroma", relative to cwd) at first run. A
# non-root container that can't write its own working directory is a bug
# regardless of whether the index is baked in.
RUN chown app:app /app
COPY --from=builder --chown=app:app /opt/venv /opt/venv

# The baked index (ADR-0015: no persistent volume, never rebuilt at
# runtime) and its matching model cache — HF_HUB_OFFLINE=1/TRANSFORMERS_OFFLINE=1
# above mean a query embedding is served only from this baked cache; the
# container never attempts a HuggingFace network call at request time,
# extending "immutable index" to "immutable model weights" for the same
# reproducibility reason.
COPY --from=builder --chown=app:app /opt/hf-cache /opt/hf-cache
COPY --from=builder --chown=app:app /app/data/chroma ./data/chroma
# TIPI source, read at request time by the verification gate (ADR-0002/0014,
# src/api/dependencies.py::_build_verification_index) — not just at index
# build time, so it ships in the runtime image too.
COPY --chown=app:app data/tipi ./data/tipi

USER app

EXPOSE 8000

# Generic, platform-agnostic: no curl/wget installed, no extra dependency —
# reuses the venv's own Python against the already-existing GET /health.
# Any orchestrator (docker run, Compose, ECS, k8s) can rely on this natively;
# Fly.io's own health-check config (Etapa 6) is additive, not a replacement.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=2)" || exit 1

# Shell form so ${PORT} expands at container start: Cloud Run/Railway inject
# PORT and require the process to respect it; Fly.io and plain `docker run`
# are fine with the default. One CMD, no platform branching.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
