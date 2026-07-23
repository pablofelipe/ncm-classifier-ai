from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.core.domain.ncm import NCM_CODE_RE


class ClassifyRequest(BaseModel):
    product_name: str = Field(
        ...,
        max_length=200,
        description="Short product name or title, as it would appear on an invoice or listing.",
        examples=["Água mineral"],
    )
    description: str = Field(
        ...,
        max_length=300,
        description=(
            "Additional product detail (packaging, volume, ingredients) that "
            "helps disambiguate similar NCM codes."
        ),
        examples=["Garrafa 500ml sem gás"],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"product_name": "Água mineral", "description": "Garrafa 500ml sem gás"}]
        }
    }


class NCMCandidate(BaseModel):
    ncm: str = Field(
        ...,
        pattern=NCM_CODE_RE.pattern,
        description="8-digit NCM fiscal code, dotted format.",
        examples=["2201.10.00"],
    )
    description: str = Field(
        ..., description="Official TIPI description for this NCM code.", examples=["Águas minerais"]
    )
    score: float = Field(
        ...,
        description=(
            "Relative ranking score from retrieval/rerank — not a calibrated "
            "probability (see ADR-0004, ADR-0011). Higher means more likely, "
            "but scores across configurations aren't comparable."
        ),
        examples=[0.71],
    )


class ClassifyResponse(BaseModel):
    confidence_label: Literal["high", "needs_review"] = Field(
        ...,
        description=(
            '"high" if the top candidate clears the confidence threshold and '
            'verification; "needs_review" otherwise — always inspect '
            "`escalation_reason` in that case."
        ),
    )
    candidates: list[NCMCandidate] = Field(
        ..., description="Always exactly 3 candidates, ranked most to least likely."
    )
    latency_ms: float = Field(
        ..., description="Time spent in the classification pipeline, measured at the HTTP layer."
    )
    escalation_reason: str | None = Field(
        None,
        description=(
            'Set only when confidence_label is "needs_review" due to a failed '
            "deterministic verification (ADR-0002/0014) — e.g. the top "
            "candidate does not exist in the loaded TIPI index. `null` otherwise."
        ),
    )

    @model_validator(mode="after")
    def _exactly_three_candidates(self) -> "ClassifyResponse":
        if len(self.candidates) != 3:
            raise ValueError(f"candidates must contain exactly 3 items, got {len(self.candidates)}")
        return self


class IndexInfo(BaseModel):
    """Diagnostic snapshot of the loaded Chroma collection (GET /info, Etapa 4).

    Everything here is already public: the collection name, entry count and
    embedder/enrich_strategy are recorded as Chroma collection metadata at
    index time (see chroma_client.index_entries); the source filename names a
    TIPI data snapshot, not a secret. Never includes credentials.
    """

    collection: str = Field(..., description="Chroma collection name currently loaded.")
    source: str = Field(
        ...,
        description="TIPI source JSON filename baked into the image at build time.",
        examples=["tipi_beverage_20260618.json"],
    )
    entries: int = Field(..., description="Number of NCM entries indexed.")
    embedder: str = Field(
        ..., description="Embedding model used to build this index (ADR-0004/0008)."
    )
    enrich_strategy: str = Field(
        ..., description="Document-text enrichment strategy used at index time (ADR-0005/0006)."
    )


class LLMInfo(BaseModel):
    """BYOK (ADR-0016) diagnostics for GET /info — never includes a credential."""

    default_provider: str = Field(
        ...,
        description=(
            "LLM provider used when a request supplies X-LLM-Api-Key "
            "without an explicit LLM-Provider header."
        ),
    )
    default_model: str = Field(
        ...,
        description=(
            "LLM model used when a request supplies X-LLM-Api-Key "
            "without an explicit LLM-Model header."
        ),
    )
    byok_supported: bool = Field(
        ...,
        description=(
            "Always true — this deployment never holds a server-side LLM credential (ADR-0015)."
        ),
    )
    byok_headers: list[str] = Field(
        ...,
        description="Request headers a caller can send to use their own LLM credential (ADR-0016).",
    )


class InfoResponse(BaseModel):
    version: str = Field(..., description="Application version.")
    index: IndexInfo = Field(..., description="Snapshot of the currently loaded retrieval index.")
    retrieval_mode: str = Field(
        ..., description='"dense" (e5-small only) or "hybrid" (BM25 + e5 via RRF, ADR-0011).'
    )
    rerank_mode: str = Field(
        ...,
        description=(
            "Server-side default reranker when no X-LLM-Api-Key is supplied "
            '— "passthrough" costs nothing and involves no LLM call.'
        ),
    )
    llm: LLMInfo = Field(..., description="Bring-your-own-LLM-credentials (ADR-0016) diagnostics.")


class RootResponse(BaseModel):
    """Landing payload for GET / — orientation for a first-time visitor, not
    a full diagnostic (that's GET /info)."""

    name: str = Field(..., description="Project name.")
    description: str = Field(..., description="One-line summary of what this API does.")
    version: str = Field(..., description="Application version.")
    deployment_profile: str = Field(
        ...,
        description=(
            "Short label for the baked-in deployment configuration — see "
            "GET /info for the full retrieval/rerank/index snapshot."
        ),
    )
    docs: str = Field(..., description="Path to the interactive API documentation (Swagger UI).")
    endpoints: dict[str, str] = Field(
        ..., description="Key endpoints, as `HTTP-METHOD path`, for quick orientation."
    )
