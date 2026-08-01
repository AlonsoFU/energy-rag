"""EXP #6 cheap-first: Intent/Entity extraction (genérico, aditivo, seguro).

Antes de buscar, el LLM extrae el concepto/organismo legal de la pregunta y se
AGREGA al lado vectorial (estilo Query2Doc: conserva la query). Compara gold_rank
base vs intent sobre v3-coloquial (target) y una muestra dev (no-regresión).

Uso: HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu \
       ./venv-gpu/bin/python -m scripts.exp_intent_extraction
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights

PROMPT = (
    "Eres experto en normativa eléctrica chilena. Dada la pregunta de un usuario, "
    "identifica el concepto, organismo o institución legal que la responde. "
    "Devuelve SOLO los términos legales formales (2 a 6 palabras), sin explicar.\n"
    "Pregunta: {q}\nTérminos legales:"
)

def _load(path, cats):
    out = []
    for l in open(path):
        d = json.loads(l)
        if d.get("category") in cats and d.get("expected_norma"):
            g = f"{d['expected_norma']}/{d['expected_articulo']}"
            ag = d.get("also_gold") or []
            out.append((d["query"], [g] + ag, d["category"]))
    return out

POS = _load("data/eval/queries_complex_v3.jsonl", {"cx_coloquial"})
REG = _load("data/eval/queries_independent.jsonl", {"indep_def", "indep_complex"})[:12]


def gold_rank(store, emb, rr, query, vec_text, golds):
    bm25 = store.search_bm25(query, top_k=50)
    vec = store.search_vector(emb.embed([vec_text])[0], top_k=50)
    fused = rrf_fusion([bm25, vec], k=60, weights=_length_weights(vec_text))[:50]
    if not fused:
        return None
    sc = rr.rerank(query, [c["contextual_text"] for c in fused], top_k=30)
    order = [fused[i] for i, _ in sc]
    gset = {(n, a) for n, a in (g.split("/", 1) for g in golds)}
    for i, c in enumerate(order):
        if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset:
            return i + 1
    return None


def run(tag, items, store, emb, rr, llm, show=False):
    b10 = i10 = 0
    for q, golds, cat in items:
        rb = gold_rank(store, emb, rr, q, q, golds)
        terms = llm.generate(PROMPT.format(q=q), max_tokens=40).text.strip().replace("\n", " ")
        ri = gold_rank(store, emb, rr, q, f"{q} {terms}", golds)
        b10 += 1 if (rb and rb <= 10) else 0
        i10 += 1 if (ri and ri <= 10) else 0
        if show:
            flag = "↑" if (ri and (not rb or ri < rb)) else ("↓" if rb and (not ri or ri > rb) else "=")
            print(f"  base={str(rb):>4} intent={str(ri):>4} {flag} {golds[0]:14s} | {q[:34]} || {terms[:45]}")
    n = len(items)
    print(f"=== {tag}: gold∈top10  base {b10}/{n} -> intent {i10}/{n} ===")


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    llm = get_llm_provider()
    print(f"reranker={type(rr).__name__}\n--- v3 COLOQUIAL (target) ---")
    run("COLOQUIAL", POS, store, emb, rr, llm, show=True)
    print("\n--- dev (no-regresión) ---")
    run("DEV-NOREG", REG, store, emb, rr, llm, show=True)


if __name__ == "__main__":
    main()
