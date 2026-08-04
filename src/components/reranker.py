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
        ml = int(os.environ.get("BGE_MAX_LENGTH", "512"))
        mk = {}
        # En GPU usar fp16: ~1.16GB (vs ~2GB fp32) → entra junto al 9b en 8GB.
        # Calidad ~igual para ranking (score 0.989 vs 0.997). Requiere torch con
        # soporte de la GPU (p.ej. cu118 en venv-gpu para Pascal sm_61).
        if dev == "cuda" and os.environ.get("BGE_FP16", "1") == "1":
            import torch
            mk["torch_dtype"] = torch.float16
        self.m = CrossEncoder("BAAI/bge-reranker-v2-m3", device=dev, max_length=ml,
                              model_kwargs=mk)

    def rerank(self, query, docs, top_k):
        if not docs:
            return []
        scores = self.m.predict([(query, d) for d in docs])
        order = sorted(range(len(docs)), key=lambda i: float(scores[i]), reverse=True)
        return [(i, float(scores[i])) for i in order[:top_k]]


class Qwen3Reranker:
    """RK1: Qwen/Qwen3-Reranker-4B (LLM-based reranker, yes/no logit). Research 2026-08:
    gap ~14pts MMTEB-R vs bge-reranker-v2-m3. Interfaz igual a BGEReranker.rerank.
    GPU fp16 (~8GB en 3090). Score = P('yes') en el ultimo token."""

    def __init__(self, model="Qwen/Qwen3-Reranker-4B", device="cuda"):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        self.tok = AutoTokenizer.from_pretrained(model, padding_side="left")
        self.model = AutoModelForCausalLM.from_pretrained(model, dtype=torch.float16).to(device).eval()
        self.dev = device
        self.yes = self.tok.convert_tokens_to_ids("yes")
        self.no = self.tok.convert_tokens_to_ids("no")
        self.pre = ('<|im_start|>system\nJudge whether the Document meets the requirements based on '
                    'the Query. Answer only "yes" or "no".<|im_end|>\n<|im_start|>user\n')
        self.suf = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"

    def rerank(self, query, docs, top_k):
        if not docs:
            return []
        import torch
        texts = [self.pre + f"<Query>: {query}\n<Document>: {d}" + self.suf for d in docs]
        scores = []
        bs = int(__import__("os").environ.get("RK_BATCH", "4"))
        ml = int(__import__("os").environ.get("RK_MAXLEN", "1024"))
        for i in range(0, len(texts), bs):
            batch = texts[i:i + bs]
            ids = self.tok(batch, return_tensors="pt", truncation=True, max_length=ml,
                           padding=True).to(self.dev)
            with torch.no_grad():
                # logits_to_keep=1: solo el ultimo token -> evita lm_head sobre toda la seq (OOM)
                lo = self.model(**ids, logits_to_keep=1).logits[:, -1, :]
            y = lo[:, self.yes]; n = lo[:, self.no]
            p = torch.softmax(torch.stack([n, y], dim=-1), dim=-1)[:, 1]
            scores.extend(p.tolist())
        order = sorted(range(len(docs)), key=lambda j: scores[j], reverse=True)
        return [(j, float(scores[j])) for j in order[:top_k]]


def get_reranker():
    """Production reranker factory. Qwen3-Reranker (RK1) si RERANKER_KIND=qwen3; BGE si
    `use_bge_reranker`; si no, Identity no-op (preserva orden RRF)."""
    import os
    from src.core.config import settings
    if os.environ.get("RERANKER_KIND") == "qwen3":
        return Qwen3Reranker()
    if getattr(settings, "use_bge_reranker", False):
        return BGEReranker()
    return IdentityReranker()
