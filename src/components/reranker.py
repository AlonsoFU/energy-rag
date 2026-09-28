"""Rerankers. EN PRODUCCION: BGEReranker (BAAI/bge-reranker-v2-m3), `use_bge_reranker=True`.

Historia, porque el default fue el contrario durante un mes:
  - 2026-05-06  Qwen3-Reranker-0.6B: le faltaba la cabeza clasificadora en el checkpoint,
                los puntajes eran ruido (-31 pp de recall). Por eso Identity fue el default.
  - 2026-05-12  bge-reranker-v2-m3 medido sobre 15 queries de alias: grounding_pass 100 % ->
                42.9 %. Muestra chica; la conclusion no aguanto.
  - 2026-06-01  campana con sets mas grandes: BGE sube gold-en-pool@5 en dev (25 -> 33) Y en
                held-out (15 -> 17), y resuelve la clase parafrasis/situacional que RRF,
                graph-boost y HyDE no movian. ADOPTADO.
  - 2026-09-21  exp #88: en GPU fp32 da el MISMO orden que en CPU (194/194, dif max 9e-6) y
                tarda 2.9 s en vez de 21.5 s, pero desplaza al LLM (49 -> 43 capas en GPU).
                Por eso el default sigue siendo CPU y la GPU se usa solo en `--buscar`,
                donde no hay respuesta que redactar (ver scripts/preguntar.py).
  - Qwen3-Reranker-4B (RK1, 2026-08): quedo plano. La clase se conserva porque la instancia
    scripts/experimentos/exp_rk1_screen.py, pero NO es un producto de la fabrica.
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


class BGEReranker:
    """BAAI/bge-reranker-v2-m3 cross-encoder. Reorders the pool by semantic
    (query, doc) relevance — the lever that, in the 2026-06-01 campaign, lifted
    gold∈pool@5 on BOTH dev (25→33) and a held-out set (15→17) and cracked the
    situational/paraphrase class, where RRF/graph-boost/HyDE could not (HyDE
    even overfit). ADOPTADO: `use_bge_reranker=True`.

    Device por `BGE_DEVICE` (default `cpu`). En GPU anda (3090) y da el mismo orden,
    pero le saca VRAM al LLM: solo `--buscar` lo prende. Carga perezosa del modelo."""

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
        # exp #88b: en GPU, devolver la memoria de activaciones apenas termina. Sin esto el BGE
        # retiene VRAM reservada y el LLM de respuestas carga con capas en CPU (49 -> 43 medido).
        if str(self.m.device).startswith("cuda"):
            import torch
            torch.cuda.empty_cache()
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
    """El de produccion: BGE si `use_bge_reranker` (hoy True); si no, Identity no-op."""
    from src.core.config import settings
    if getattr(settings, "use_bge_reranker", False):
        return BGEReranker()
    return IdentityReranker()
