"""Prototipo (retrieval-only) del lever DESCOMPOSICIÓN DE QUERY para queries
compositivas (distractor + multi-parte), el frente que ni BGE ni multi_query
resolvieron.

Idea: el LLM parte la query en sub-preguntas atómicas; recuperamos por cada una
(BM25+vector+RRF), unimos los pools (dedup por artículo), y rerankeamos la unión
con BGE. Para distractor, la sub-pregunta núcleo queda sin el término-señuelo;
para multi-parte, cada parte se recupera por separado.

A/B por query: baseline (query sola → BM25+vector+BGE) vs descompuesta. Mide
gold∈pool@5/10. NO toca producción. Sets por argv (default dev+extremo).
"""
import json, os, sys
from pathlib import Path
from collections import defaultdict

from src.components.embedder import Qwen3Embedder
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights
from src.pipelines.grounding import _normalize_art
from scripts.campaign_sweep import BGEReranker

KS = [5, 10]
SETS = sys.argv[1:] or ["data/eval/queries_independent.jsonl", "data/eval/queries_extreme.jsonl"]

DECOMP_SYS = (
    "Partí la pregunta en sub-preguntas ATÓMICas (1 a 3), cada una autocontenida y sobre UN solo "
    "asunto. Si la pregunta menciona algo solo como CONTEXTO (ej. 'más allá del coordinador, ¿quién "
    "resuelve X?'), la sub-pregunta núcleo debe quedar SIN ese contexto-señuelo (solo '¿quién resuelve "
    "X?'). Si ya es atómica, devolvela igual. Una sub-pregunta por línea, sin numeración ni texto extra."
)


def decompose(llm, q):
    r = llm.generate(f"Pregunta: {q}\n\nSub-preguntas:", system=DECOMP_SYS,
                     temperature=0.0, max_tokens=160)
    subs = [l.strip(" -•\t") for l in (r.text or "").splitlines() if l.strip()]
    subs = [s for s in subs if len(s) > 8][:3]
    return subs or [q]


def pool_for(store, emb, text, depth=50):
    bm = store.search_bm25(text, top_k=depth)
    v = store.search_vector(emb.embed([text])[0], top_k=depth)
    return rrf_fusion([bm, v], k=60, weights=_length_weights(text))[:depth]


def rank_after_bge(bge, query, cands, k=max(KS)):
    if not cands:
        return None, []
    scored = bge.rerank(query, [c["contextual_text"] for c in cands], top_k=len(cands))
    order = [cands[i] for i, _ in scored][:k]
    return order


def _rank(docs, norma, art):
    ta = _normalize_art(str(art))
    for i, d in enumerate(docs):
        if str(d.get("id_norma")) == str(norma) and _normalize_art(str(d.get("articulo_numero"))) == ta:
            return i + 1
    return None


def main():
    emb = Qwen3Embedder(); store = PostgresStore(); llm = get_llm_provider()
    bge = BGEReranker()
    for path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        pos = [r for r in rows if r.get("expected_norma")]
        agg = defaultdict(lambda: {"n": 0, "base@5": 0, "dec@5": 0})
        print(f"\n==== {Path(path).stem} (n={len(pos)}) ====")
        for q in pos:
            gold = (str(q["expected_norma"]), str(q["expected_articulo"])); cat = q["category"]
            # baseline: query sola
            base = rank_after_bge(bge, q["query"], pool_for(store, emb, q["query"]))
            # descompuesta: unir pools de sub-preguntas, rerank con la query original
            subs = decompose(llm, q["query"])
            union = {}
            for s in subs:
                for c in pool_for(store, emb, s):
                    union[c["articulo_id"]] = c
            dec = rank_after_bge(bge, q["query"], list(union.values()))
            rb, rd = _rank(base, *gold), _rank(dec, *gold)
            a = agg[cat]; a["n"] += 1
            a["base@5"] += bool(rb and rb <= 5); a["dec@5"] += bool(rd and rd <= 5)
            flag = "↑" if (rd and rd <= 5) and not (rb and rb <= 5) else ("↓" if (rb and rb <= 5) and not (rd and rd <= 5) else " ")
            print(f"[{flag}] {cat:16s} gold={gold[0]}/{gold[1]:6s} base_rk={rb} dec_rk={rd} subs={len(subs)}")
        print(f"  -- resumen {Path(path).stem} --")
        tb = td = tn = 0
        for c, a in sorted(agg.items()):
            print(f"  {c:18s} base@5={a['base@5']}/{a['n']}  dec@5={a['dec@5']}/{a['n']}")
            tn += a["n"]; tb += a["base@5"]; td += a["dec@5"]
        print(f"  {'TOTAL':18s} base@5={tb}/{tn}  dec@5={td}/{tn}  (Δ={td-tb:+d})")


if __name__ == "__main__":
    main()
