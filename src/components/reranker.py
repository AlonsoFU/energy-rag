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


class BGEReranker:
    """BAAI/bge-reranker-v2-m3 cross-encoder. Reorders the pool by semantic
    (query, doc) relevance — the lever that, in the 2026-06-01 campaign, lifted
    gold∈pool@5 on BOTH dev (25→33) and a held-out set (15→17) and cracked the
    situational/paraphrase class, where RRF/graph-boost/HyDE could not (HyDE
    even overfit). Gated by `use_bge_reranker` (default OFF) until the
    generation eval confirms the recall gain survives as cita_ok (BGE historically
    hurt the LLM's citation discipline — that's what the eval checks).

    CPU only: GTX 1080 (Pascal sm_61) lacks GPU kernels for this cross-encoder
    ('no kernel image'). Lazy model load so importing this module stays cheap."""

    def __init__(self, device: str | None = None):
        import os
        from sentence_transformers import CrossEncoder
        dev = device or os.environ.get("BGE_DEVICE", "cpu")
        self.m = CrossEncoder("BAAI/bge-reranker-v2-m3", device=dev, max_length=512)

    def rerank(self, query, docs, top_k):
        if not docs:
            return []
        scores = self.m.predict([(query, d) for d in docs])
        order = sorted(range(len(docs)), key=lambda i: float(scores[i]), reverse=True)
        return [(i, float(scores[i])) for i in order[:top_k]]


def get_reranker():
    """Production reranker factory. BGE when `use_bge_reranker` is on, else the
    Identity no-op (preserves RRF order — the prior default)."""
    from src.core.config import settings
    if getattr(settings, "use_bge_reranker", False):
        return BGEReranker()
    return IdentityReranker()
