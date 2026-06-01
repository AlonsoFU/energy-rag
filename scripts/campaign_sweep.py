"""Harness de la campaña de experimentación (retrieval-only).

Para una CONFIG (controlada por env: HYDE_IN_SIMPLE, RETRIEVAL_POOL_DEPTH,
GRAPH_BOOST_ALL, etc. + flags nuevos), mide el RANGO del gold y gold∈pool@5/10/20
sobre los dos sets (dev=queries_independent, test=queries_holdout). Usa
SimpleRetriever (determinista, sin ruteo) para comparar limpio el poder de
retrieval de cada lever. Guarda JSON en data/eval/results/campaign/.

Uso: python -m scripts.campaign_sweep <config_label> [set1.jsonl set2.jsonl ...]
"""
import json
import os
import sys
from pathlib import Path
from collections import defaultdict

from src.components.embedder import Qwen3Embedder  # sets HF_HUB_OFFLINE
from src.components.reranker import Qwen3Reranker


class BGEReranker:
    """Cross-encoder reranker (EXP). Reorders the pool by semantic (query, doc)
    relevance — the lever for paraphrase→operative-article (situacional), which
    RRF/graph-boost can't promote. Retrieval-only test; NOT the production
    reranker (BGE hurt the LLM's citation discipline historically, but that was
    grounding, not recall@5 — measure recall here)."""

    def __init__(self, device: str | None = None):
        from sentence_transformers import CrossEncoder
        # Pascal (GTX 1080, sm_61): el cross-encoder BGE tira "no kernel image"
        # en GPU (a diferencia del embedder Qwen que evita fp16). CPU por default.
        # max_length por env (EXP Fase 2): bge-reranker-v2-m3 aguanta 8192; 512
        # trunca ~30% de chunks. Subirlo = más cómputo en CPU (costo, no bloqueo).
        dev = device or os.environ.get("BGE_DEVICE", "cpu")
        ml = int(os.environ.get("BGE_MAX_LENGTH", "512"))
        self.m = CrossEncoder("BAAI/bge-reranker-v2-m3", device=dev, max_length=ml)

    def rerank(self, query, docs, top_k):
        if not docs:
            return []
        scores = self.m.predict([(query, d) for d in docs])
        order = sorted(range(len(docs)), key=lambda i: float(scores[i]), reverse=True)
        return [(i, float(scores[i])) for i in order[:top_k]]
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.core import config as cfg
from src.pipelines.grounding import _normalize_art

KS = [5, 10, 20]
OUTDIR = Path("data/eval/results/campaign")
DEFAULT_SETS = ["data/eval/queries_independent.jsonl", "data/eval/queries_holdout.jsonl"]


def _golds(q):
    """Lista de (norma, art) aceptados: expected + also_gold (multi-gold). Una
    pregunta puede tener varios artículos válidos (gold discutible/complementario)."""
    out = [(str(q["expected_norma"]), str(q["expected_articulo"]))]
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1)
        out.append((n, a))
    return out


def _rank(docs, golds):
    """Mejor (menor) rango entre cualquiera de los gold aceptados."""
    norm = {(str(n), _normalize_art(str(a))) for n, a in golds}
    for i, d in enumerate(docs):
        if (str(d.get("id_norma")), _normalize_art(str(d.get("articulo_numero")))) in norm:
            return i + 1
    return None


def run_set(retr, path):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    pos = [r for r in rows if r.get("expected_norma")]
    by_cat = defaultdict(lambda: {"n": 0, **{f"@{k}": 0 for k in KS}})
    detail = []
    for q in pos:
        gold = (str(q["expected_norma"]), str(q["expected_articulo"]))
        docs = retr.retrieve(q["query"], top_k=max(KS))
        rk = _rank(docs, _golds(q))
        cat = q["category"]
        by_cat[cat]["n"] += 1
        for k in KS:
            if rk and rk <= k:
                by_cat[cat][f"@{k}"] += 1
        detail.append({"q": q["query"], "cat": cat, "gold": f"{gold[0]}/{gold[1]}", "rank": rk})
    tot = {"n": len(pos), **{f"@{k}": sum(1 for d in detail if d["rank"] and d["rank"] <= k) for k in KS}}
    return {"by_cat": dict(by_cat), "total": tot, "detail": detail}


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "unlabeled"
    sets = sys.argv[2:] or DEFAULT_SETS
    config = {
        "hyde_in_simple": getattr(cfg.settings, "hyde_in_simple", False),
        "retrieval_pool_depth": cfg.settings.retrieval_pool_depth,
        "graph_boost_all": getattr(cfg.settings, "graph_boost_all", False),
        "inject_curated_definitions": getattr(cfg.settings, "inject_curated_definitions", True),
    }
    pool = cfg.settings.retrieval_pool_depth
    e = Qwen3Embedder()
    rk = os.environ.get("CAMPAIGN_RERANKER", "identity").lower()
    r = BGEReranker() if rk == "bge" else Qwen3Reranker()
    config["reranker"] = rk
    store = PostgresStore()
    llm = get_llm_provider()
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    if os.environ.get("CAMPAIGN_RETRIEVER", "simple").lower() == "adaptive":
        from src.pipelines.retrieve import ComplexRetriever, AdaptiveRetriever
        from src.routing.adaptive import AdaptiveRouter
        complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
        router = AdaptiveRouter(); router.train_default()
        adaptive = AdaptiveRetriever(simple, complejo, router)
        config["retriever"] = "adaptive"
        class _Wrap:  # AdaptiveRetriever.retrieve devuelve (branch, docs)
            def retrieve(self, q, top_k=5): return adaptive.retrieve(q, top_k=top_k)[1]
        retr = _Wrap()
    else:
        config["retriever"] = "simple"
        retr = simple

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"=== CONFIG {label} === {config}")
    out = {"label": label, "config": config, "sets": {}}
    for s in sets:
        res = run_set(retr, s)
        name = Path(s).stem
        out["sets"][name] = res
        t = res["total"]
        print(f"\n[{name}] n={t['n']}  " + "  ".join(f"@{k}={t[f'@{k}']}/{t['n']}" for k in KS))
        for cat, c in sorted(res["by_cat"].items()):
            print(f"    {cat:20s} n={c['n']:2d}  " + " ".join(f"@{k}={c[f'@{k}']}" for k in KS))
    fp = OUTDIR / f"{label}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n-> {fp}")


if __name__ == "__main__":
    main()
