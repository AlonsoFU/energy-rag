"""EXP: reformulación SELECTIVA (detecta coloquial → reescribe legal; deja legal igual).
Estándar 2025 (PreQRAG / "not all queries need rewriting"). Un solo call LLM condicional,
aditivo (conserva la query). Mide gold∈top10 base vs selectiva en coloquial + dev.

Uso: HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu \
       ./venv-gpu/bin/python -m scripts.exp_selective_reform
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights

PROMPT = (
    "Eres experto en normativa eléctrica chilena. Si la siguiente pregunta está en "
    "lenguaje COTIDIANO/coloquial, reescríbela en términos legales formales del sector "
    "eléctrico (organismos, conceptos, artículos relevantes). Si la pregunta YA usa "
    "lenguaje legal/técnico, responde EXACTAMENTE la palabra: IGUAL.\n"
    "No expliques. Solo la reescritura o IGUAL.\n"
    "Pregunta: {q}\nReescritura:"
)


def _load(path, cats):
    out = []
    for l in open(path):
        d = json.loads(l)
        if d.get("category") in cats and d.get("expected_norma"):
            out.append((d["query"], [f"{d['expected_norma']}/{d['expected_articulo']}"] + (d.get("also_gold") or [])))
    return out

POS = _load("data/eval/queries_coloquial_v2.jsonl", {"cx_coloquial"})
REG = _load("data/eval/queries_independent.jsonl", {"indep_def", "indep_complex"})[:12]


def gold_rank(store, emb, rr, query, vec_text, golds):
    bm = store.search_bm25(query, top_k=50)
    vec = store.search_vector(emb.embed([vec_text])[0], top_k=50)
    fused = rrf_fusion([bm, vec], k=60, weights=_length_weights(vec_text))[:50]
    sc = rr.rerank(query, [c["contextual_text"] for c in fused], top_k=30)
    order = [fused[i] for i, _ in sc]
    gset = {(n, a) for n, a in (g.split("/", 1) for g in golds)}
    return next((i + 1 for i, c in enumerate(order) if (str(c.get("id_norma")), str(c.get("articulo_numero"))) in gset), None)


def run(tag, items, store, emb, rr, llm):
    b10 = s10 = n_reform = 0
    for q, golds in items:
        rb = gold_rank(store, emb, rr, q, q, golds)
        rw = llm.generate(PROMPT.format(q=q), max_tokens=60).text.strip()
        reform = rw.upper() != "IGUAL" and len(rw) > 3
        vec_text = f"{q} {rw}" if reform else q
        n_reform += 1 if reform else 0
        rs = gold_rank(store, emb, rr, q, vec_text, golds)
        b10 += 1 if (rb and rb <= 10) else 0
        s10 += 1 if (rs and rs <= 10) else 0
        flag = "↑" if (rs and rs <= 10 and (not rb or rb > 10)) else ("↓" if rb and rb <= 10 and (not rs or rs > 10) else "")
        print(f"  base={str(rb):>4} select={str(rs):>4} {flag} {'REF' if reform else 'igual':5s} | {q[:34]} || {rw[:40]}")
    n = len(items)
    print(f"=== {tag}: gold∈top10 base {b10}/{n} -> selectiva {s10}/{n} ({n_reform} reformuladas) ===\n")


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    llm = get_llm_provider()
    print("--- COLOQUIAL (39) ---"); run("COLOQUIAL", POS, store, emb, rr, llm)
    print("--- DEV no-reg (12) ---"); run("DEV", REG, store, emb, rr, llm)


if __name__ == "__main__":
    main()
