"""EXP end-to-end: gate LÉXICO (actual) vs SEMÁNTICO (bge_max<τ).

Mide cita_ok / answered / refused sobre:
  COL  = coloquial in-domain (deben responder y citar gold)
  NEG1 = off-topic claro (deben rechazar)
  NEG2 = eléctrico-pero-factual (deben rechazar; caso difícil)
  REG  = muestra in-domain de dev (no-regresión: no empezar a rechazar)
  REGN = negativos de dev/holdout (no-regresión: seguir rechazando)

Modo léxico: generate_answer normal (is_off_topic léxico). Modo semántico: refuse si
bge_max<τ; si pasa, generar con is_off_topic parcheado a False (aísla el gate semántico).

Uso: HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu \
       ./venv-gpu/bin/python -m scripts.exp_gate_generation 0.01
"""
import json
import sys
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights, hierarchical_expand
from src.pipelines import off_topic as ot
from src.pipelines import generate as gen
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art

TAU = float(sys.argv[1]) if len(sys.argv) > 1 else 0.01

COL = [(json.loads(l)["query"], f"{json.loads(l)['expected_norma']}/{json.loads(l)['expected_articulo']}",
        [g for g in (json.loads(l).get("also_gold") or [])])
       for l in open("data/eval/queries_complex_v3.jsonl") if json.loads(l)["category"] == "cx_coloquial"]
NEG1 = ["receta de pan amasado", "quién ganó el mundial 2022", "cuántos planetas tiene el sistema solar",
        "cómo se cambia una rueda pinchada del auto", "receta de pisco sour"]
NEG2 = ["cuál es la tarifa del kilowatt-hora residencial en Atacama este mes",
        "qué empresa ganó la última licitación de suministro eléctrico",
        "cuántos megawatts de potencia instalada tiene la central Ralco"]
# no-regresión: in-domain de dev (deben responder y citar) + negativos (deben rechazar)
_dev = [json.loads(l) for l in open("data/eval/queries_independent.jsonl")]
REG = [(d["query"], f"{d['expected_norma']}/{d['expected_articulo']}", [])
       for d in _dev if d.get("expected_norma") and d["category"] in ("indep_def", "indep_complex")][:12]
REGN = [d["query"] for d in _dev if d["category"] in ("indep_offcorpus", "indep_ambiguo")]


def retrieve(store, emb, rr, q, top_k=10):
    bm25 = store.search_bm25(q, top_k=50)
    vec = store.search_vector(emb.embed([q])[0], top_k=50)
    fused = rrf_fusion([bm25, vec], k=60, weights=_length_weights(q))[:50]
    if not fused:
        return [], 0.0
    scored = rr.rerank(q, [c["contextual_text"] for c in fused], top_k=30)
    bge_max = max((s for _, s in scored), default=0.0)
    fused = [{**fused[i], "score": float(s)} for i, s in scored]
    return hierarchical_expand(fused)[:top_k], bge_max


def cita_ok(text, golds):
    norm = {(str(n), _normalize_art(str(a))) for n, a in golds}
    return any((str(n), _normalize_art(str(a))) in norm for n, a in extract_citations(text))


def run(mode, store, emb, rr, llm):
    orig = ot.is_off_topic
    res = {k: dict(n=0, answered=0, cita=0, refused=0) for k in ("COL", "NEG1", "NEG2", "REG", "REGN")}
    def golds_of(g, ag): return [tuple(g.split("/", 1))] + [tuple(x.split("/", 1)) for x in ag]
    items = ([("COL", q, g, ag) for q, g, ag in COL] + [("NEG1", q, None, []) for q in NEG1]
             + [("NEG2", q, None, []) for q in NEG2] + [("REG", q, g, []) for q, g, _ in REG]
             + [("REGN", q, None, []) for q in REGN])
    for grp, q, g, ag in items:
        docs, bge = retrieve(store, emb, rr, q)
        r = res[grp]; r["n"] += 1
        if mode == "semantic":
            gen.is_off_topic = lambda _q: False  # desactiva léxico EN generate; gate = bge<τ
            refused = bge < TAU
        else:
            gen.is_off_topic = orig
            refused = orig(q)
        if refused:
            r["refused"] += 1; gen.is_off_topic = orig; continue
        out = generate_answer(q, docs, llm=llm, initial_top=10)
        gen.is_off_topic = orig
        txt = out["text"]
        if ot.REFUSAL_TEXT.lower() in txt.lower():
            r["refused"] += 1
        else:
            r["answered"] += 1
            if g and cita_ok(txt, golds_of(g, ag)):
                r["cita"] += 1
    return res


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    llm = get_llm_provider()
    print(f"=== GATE EXP  τ={TAU}  reranker={type(rr).__name__} ===")
    for mode in ("lexical", "semantic"):
        res = run(mode, store, emb, rr, llm)
        print(f"\n--- modo {mode} ---")
        for k, r in res.items():
            print(f"  {k:5s} n={r['n']:2d} answered={r['answered']:2d} cita_ok={r['cita']:2d} refused={r['refused']:2d}")


if __name__ == "__main__":
    main()
