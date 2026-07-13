"""Gemini Flash LLM rerank adapter (ADR-0013)."""

import json
import logging
import re
from typing import TYPE_CHECKING

from src.config import settings
from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.llm.gemini_client import _client

if TYPE_CHECKING:
    import google.genai as genai

logger = logging.getLogger(__name__)

_TOP_K = 5

_SYSTEM = (
    "Você é um classificador fiscal brasileiro. "
    "Dado um produto e candidatos NCM da TIPI, "
    "retorne APENAS JSON com os códigos reordenados do mais ao menos provável."
)


def _build_prompt(query: ProductQuery, pool: list[ClassificationCandidate]) -> str:
    lines = [f"Produto: {query.product_name}"]
    if query.description:
        lines.append(f"Descrição: {query.description}")
    lines.append("")
    lines.append("Candidatos NCM (código — descrição fiscal):")
    for i, c in enumerate(pool):
        lines.append(f"{i + 1}. {c.ncm_code} — {c.description}")
    lines.append("")
    lines.append('Responda APENAS com JSON: {"ranked": ["NNNNNNNN", ...]}')
    return "\n".join(lines)


class GeminiRerankAdapter:
    """LLM rerank via Gemini Flash (ADR-0013).

    Sends the top-k candidates to Gemini Flash with a PT-BR fiscal classification
    prompt and reorders them by the returned JSON ranking. Falls back to the
    original order if the response cannot be parsed, logging the raw output.

    Raises ConfigurationError on the first rerank() call when GEMINI_API_KEY
    is absent and no client was injected.
    """

    def __init__(self, client: "genai.Client | None" = None) -> None:
        self._override = client
        self._cached: genai.Client | None = None

    def _get_client(self) -> "genai.Client":
        if self._override is not None:
            return self._override
        if self._cached is None:
            self._cached = _client()  # raises ConfigurationError when no key
        return self._cached

    def rerank(
        self,
        query: ProductQuery,
        candidates: list[ClassificationCandidate],
    ) -> list[ClassificationCandidate]:
        if not candidates:
            return []

        client = self._get_client()
        pool = candidates[:_TOP_K]
        rest = candidates[_TOP_K:]

        prompt = _build_prompt(query, pool)
        response = client.models.generate_content(
            model=settings.gemini_flash_model,
            contents=prompt,
            config={
                "system_instruction": _SYSTEM,
                "response_mime_type": "application/json",
            },
        )
        raw: str = (response.text or "").strip()
        # Strip markdown fences defensively (some model versions ignore mime type).
        cleaned = re.sub(r"^```[a-z]*\n?", "", raw)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            ranked_codes: list[str] = data["ranked"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "GeminiRerankAdapter: malformed response %r — %s; falling back to original order",
                cleaned,
                exc,
            )
            return candidates

        index = {c.ncm_code: c for c in pool}
        reranked = [index.pop(code) for code in ranked_codes if code in index]
        reranked.extend(index.values())  # pool candidates not mentioned in ranked list
        reranked.extend(rest)  # candidates beyond top-k stay at end
        return reranked
