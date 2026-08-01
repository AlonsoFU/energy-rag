"""SCREEN retrieval-only del Exp #4 (concept_inference).

Hipótesis: inferir el CONCEPTO legal exacto (corto, sin alucinar leyes) y añadirlo
ADITIVO vector-only mete el gold coloquial al pool donde la reformulación verbosa no.

Mide gold∈top{5,10,20} con concept_inference OFF vs ON, sobre SimpleRetriever (señal
limpia, sin la dilución de complejo). Sin generación LLM → rápido (~1 call inferencia
por query del lado ON). coloquial = target; dev = no-regresión.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_concept_inference
Solo con GPU+RAM libres (carga Ollama 9b para la inferencia, BGE CPU, embedder CPU).
"""
import json
from pathlib import Path

from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.grounding import _normalize_art
from src.core import config as cfg

OUTDIR = Path("data/eval/results/concept_inference")
SETS = [
    ("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
    ("dev",       "data/eval/queries_independent.jsonl"),
]
TOPS = [5, 10, 20]


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1)
        out.add((n, _normalize_art(a)))
    return out


def _hit(docs, golds, n):
    for d in docs[:n]:
        if (str(d.get("id_norma")), _normalize_art(str(d.get("articulo_numero")))) in golds:
            return True
    return False


def main():
    e = Qwen3Embedder()
    r = get_reranker()
    store = PostgresStore()
    llm = get_llm_provider()
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print("=== SCREEN concept_inference (retrieval-only, SimpleRetriever) ===", flush=True)

    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        agg = {f"off@{n}": 0 for n in TOPS}
        agg.update({f"on@{n}": 0 for n in TOPS})
        detail = []
        for q in rows:
            golds = _golds(q)
            # OFF
            cfg.settings.concept_inference = False
            docs_off = retr.retrieve(q["query"], top_k=max(TOPS))
            # ON (la inferencia ocurre dentro de _search_text; guarda los términos)
            cfg.settings.concept_inference = True
            docs_on = retr.retrieve(q["query"], top_k=max(TOPS))
            terms = getattr(retr, "_last_concept_terms", "")
            cfg.settings.concept_inference = False
            row = {"q": q["query"][:60], "gold": sorted(golds), "terms": terms, "off": {}, "on": {}}
            for n in TOPS:
                ho = _hit(docs_off, golds, n); hn = _hit(docs_on, golds, n)
                agg[f"off@{n}"] += ho; agg[f"on@{n}"] += hn
                row["off"][n] = ho; row["on"][n] = hn
            detail.append(row)
            print(f"[{setname}] off@10={agg['off@10']} on@10={agg['on@10']} "
                  f"| {q['query'][:38]} -> {terms[:40]}", flush=True)
        out = {"set": setname, "n": len(rows), "agg": agg, "detail": detail}
        (OUTDIR / f"{setname}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"\n=== {setname} n={len(rows)} ===", flush=True)
        for n in TOPS:
            d = agg[f"on@{n}"] - agg[f"off@{n}"]
            print(f"  top{n:>2}: OFF={agg[f'off@{n}']:2d}  ON={agg[f'on@{n}']:2d}  ({'+' if d>=0 else ''}{d})", flush=True)
        print(f"-> {OUTDIR / f'{setname}.json'}\n", flush=True)


if __name__ == "__main__":
    main()
