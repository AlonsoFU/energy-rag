"""Eval de GENERACIÓN para la campaña: ¿el +recall@5 de BGE se traduce en +cita_ok?

Corre la pipeline de producción (AdaptiveRetriever -> generate_answer) sobre un
set, y mide por categoría: answered (no-rechazo), grounding_pass, y CITA_OK
(la respuesta cita el (norma, art) gold). El reranker/flags salen del env
(USE_BGE_RERANKER, TOP_RERANK_OVERRIDE, etc.) → correr 2 veces (off/on) y comparar.

Uso: python -m scripts.campaign_generation_eval <label> [set.jsonl] [top_k]
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.core import config as cfg

OUTDIR = Path("data/eval/results/campaign")


def _cited(citations, golds):
    """cita_ok si se cita CUALQUIERA de los gold aceptados (multi-gold)."""
    norm = {(str(n), _normalize_art(str(a))) for n, a in golds}
    return any((str(n), _normalize_art(str(a))) in norm for n, a in citations)


def _golds(q):
    out = [(str(q["expected_norma"]), str(q["expected_articulo"]))]
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.append((n, a))
    return out


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "gen"
    eval_file = sys.argv[2] if len(sys.argv) > 2 else "data/eval/queries_holdout.jsonl"
    top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    pool = cfg.settings.retrieval_pool_depth
    e = Qwen3Embedder()
    r = get_reranker()  # BGE si use_bge_reranker
    store = PostgresStore()
    llm = get_llm_provider()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    rows = [json.loads(l) for l in Path(eval_file).read_text().splitlines() if l.strip()]
    config = {"use_bge_reranker": cfg.settings.use_bge_reranker,
              "top_rerank_override": cfg.settings.top_rerank_override,
              "hyde_in_simple": cfg.settings.hyde_in_simple, "top_k": top_k}
    print(f"=== GEN {label} === {config}")

    by_cat = defaultdict(lambda: {"n": 0, "answered": 0, "grounded": 0, "cita_ok": 0})
    neg = {"n": 0, "refused_ok": 0}
    detail = []
    for q in rows:
        exp_n, exp_a = q.get("expected_norma"), q.get("expected_articulo")
        branch, docs = adaptive.retrieve(q["query"], top_k=top_k)
        res = generate_answer(q["query"], docs, llm=llm)
        txt = res["text"]
        cits = extract_citations(txt)
        from src.pipelines.off_topic import REFUSAL_TEXT
        refused = REFUSAL_TEXT.lower() in txt.lower()
        if exp_n is None:  # negativa
            neg["n"] += 1
            neg["refused_ok"] += refused
            detail.append({"q": q["query"], "neg": True, "refused": refused})
            continue
        cat = q["category"]
        c = by_cat[cat]; c["n"] += 1
        c["answered"] += (not refused)
        c["grounded"] += bool(res["grounding_pass"])
        ok = _cited(cits, _golds(q))
        c["cita_ok"] += ok
        detail.append({"q": q["query"], "cat": cat, "gold": f"{exp_n}/{exp_a}",
                       "cita_ok": ok, "refused": refused, "cits": [f"{n}/{a}" for n, a in cits]})

    tot = {k: sum(c[k] for c in by_cat.values()) for k in ["n", "answered", "grounded", "cita_ok"]}
    print(f"\n[{Path(eval_file).stem}] positivas n={tot['n']}  "
          f"cita_ok={tot['cita_ok']}/{tot['n']}  grounded={tot['grounded']}  answered={tot['answered']}")
    for cat, c in sorted(by_cat.items()):
        print(f"    {cat:16s} n={c['n']:2d}  cita_ok={c['cita_ok']}  grounded={c['grounded']}  answered={c['answered']}")
    print(f"  negativas: refused_ok={neg['refused_ok']}/{neg['n']}")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    out = {"label": label, "config": config, "eval_file": eval_file,
           "total": tot, "by_cat": dict(by_cat), "neg": neg, "detail": detail}
    (OUTDIR / f"{label}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"-> {OUTDIR / f'{label}.json'}")


if __name__ == "__main__":
    main()
