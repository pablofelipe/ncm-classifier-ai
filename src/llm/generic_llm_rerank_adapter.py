"""Provider-agnostic LLM rerank adapter (ADR-0016).

Same prompt/reordering/fallback logic as the earlier Gemini-specific
GeminiRerankAdapter (ADR-0013), but talks to an injected LLMClient instead of
the google-genai SDK directly — the prompt itself is already vendor-neutral
PT-BR fiscal text, nothing Gemini-specific about it.
"""

import json
import logging
import re

from src.core.domain.ncm import ClassificationCandidate, ProductQuery
from src.llm.llm_client import LLMClient

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


class GenericLLMRerankAdapter:
    """LLM rerank via any LLMClient (ADR-0016).

    Sends the top-k candidates to the injected LLMClient with a PT-BR fiscal
    classification prompt and reorders them by the returned JSON ranking.
    Falls back to the original order if the response cannot be parsed,
    logging the raw output. Vendor-agnostic: the credential/SDK concern lives
    entirely inside whichever LLMClient is injected.
    """

    def __init__(self, client: LLMClient, *, model: str) -> None:
        self._client = client
        self._model = model

    def rerank(
        self,
        query: ProductQuery,
        candidates: list[ClassificationCandidate],
    ) -> list[ClassificationCandidate]:
        if not candidates:
            return []

        pool = candidates[:_TOP_K]
        rest = candidates[_TOP_K:]

        prompt = _build_prompt(query, pool)
        raw = self._client.generate(
            model=self._model,
            system_instruction=_SYSTEM,
            prompt=prompt,
            response_format="application/json",
        )
        # Strip markdown fences defensively (some model versions ignore mime type).
        cleaned = re.sub(r"^```[a-z]*\n?", "", raw)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            ranked_codes: list[str] = data["ranked"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning(
                "GenericLLMRerankAdapter: malformed response %r — %s; "
                "falling back to original order",
                cleaned,
                exc,
            )
            return candidates

        index = {c.ncm_code: c for c in pool}
        reranked = [index.pop(code) for code in ranked_codes if code in index]
        reranked.extend(index.values())  # pool candidates not mentioned in ranked list
        reranked.extend(rest)  # candidates beyond top-k stay at end
        return reranked
