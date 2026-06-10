"""Embedding model identity for the ChromaDB retrieval adapter (ADR-0004).

These constants pin the exact embedding model and its HuggingFace revision used
both to build the index and to embed queries. They live here, in the retrieval
adapter layer, rather than in ``config.py`` on purpose: the revision is an
invariant of the indexed artifact, not an environment-specific setting. If it
were overridable via an environment variable, a deployment could silently
desynchronize the index from the evaluated baseline.

Model:    intfloat/multilingual-e5-small (multilingual, retrieval-native, 384-dim)
Revision: pinned below; captured 2026-04-02 (HuggingFace ``lastModified``).

Re-confirm the pin with:

    python -c "from huggingface_hub import HfApi; \
        print(HfApi().model_info('intfloat/multilingual-e5-small').sha)"

See ADR-0004 for the embedder selection rationale and the eval baseline.
"""

EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
EMBEDDING_DIM = 384
