"""Identity reranker — preserves RRF order.

Tried two real rerankers and neither improved this pipeline:

  1. Qwen3-Reranker-0.6B: classifier head missing from checkpoint → scores
     are random noise. Eval 2026-05-06 confirmed -31pp recall when enabled.

  2. BAAI/bge-reranker-v2-m3: working cross-encoder, but eval 2026-05-12 on
     15 alias queries showed grounding_pass DROPPING from 100% to 42.9% (of 7
     generations) while recall stayed at 46.7%. Diagnosis: BGE reorders docs
     2-10 by general semantic relevance, but the LLM benefits more from RRF
     order in legal-QA-with-verbatim-citations — the "most relevant" doc by
     BGE isn't always the most definitional one. The JSON schema enum built
     from BGE order steers the LLM toward less canonical citations.

Identity rerank keeps the RRF order, which empirically beats both alternatives
for this corpus + task. Keep the door open for future experiments (e.g. BGE
as a filter for top-50 → top-20 instead of as a reorderer for top-10).
"""
from src.core.config import settings


class IdentityReranker:
    """No-op reranker: preserves the input order from RRF fusion."""

    def __init__(self, *args, **kwargs):
        # Accept (model_name, device) for backwards-compatible construction
        # at call sites that pass them. No actual model loaded.
        pass

    def rerank(
        self, query: str, docs: list[str], top_k: int
    ) -> list[tuple[int, float]]:
        if not docs:
            return []
        n = min(len(docs), top_k)
        return [(i, 1.0 / (i + 1)) for i in range(n)]


# Backwards-compatible alias: existing code imports Qwen3Reranker.
Qwen3Reranker = IdentityReranker
