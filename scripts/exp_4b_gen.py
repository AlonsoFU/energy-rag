"""Generation eval del embedder 4B: ¿el +retrieval (gold∈top10 coloquial +7) convierte
a cita_ok? ¿el holdout −3 se recupera con BM25+BGE rerank?

Dos fases para evitar el swap Ollama (4B-embed y 9B-gen no caben juntos en 8GB):
  FASE A (Ollama=4B): recuperar docs OFF (0.6B, CPU) y ON (4B, Ollama) para todas las
                      queries con SimpleRetriever (sin expansión LLM → no carga 9B). Cachea.
  FASE B (Ollama=9B): generar desde los docs cacheados, medir cita_ok OFF vs ON.

Usa SimpleRetriever (aísla el embedder + evita 9B en retrieval). Caveat: producción rutea
coloquial a complejo; esto mide el efecto LIMPIO del embedder en el híbrido simple.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_4b_gen [top_k]
Requiere embedding_4b poblada + Ollama qwen3-embedding:4b + qwen3.5:9b.
"""
import json, sys
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/emb4b_gen")
SETS = [
    ("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
    ("dev",       "data/eval/queries_independent.jsonl"),
    ("holdout",   "data/eval/queries_holdout.jsonl"),
]


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _cited(cits, golds):
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits)


def main():
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)

    # ---- FASE A: retrieval (Ollama carga 4B; 0.6B en CPU; sin 9B) ----
    print("=== FASE A: retrieval OFF(0.6B) + ON(4B) ===", flush=True)
    cache = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        for q in rows:
            cfg.settings.embed_4b_dense = False
            off_docs = retr.retrieve(q["query"], top_k=top_k)
            cfg.settings.embed_4b_dense = True
            cfg.settings.embed_4b_dim = int(sys.argv[2]) if len(sys.argv) > 2 else 2560
            on_docs = retr.retrieve(q["query"], top_k=top_k)
            cfg.settings.embed_4b_dense = False
            cache.append({"set": setname, "q": q["query"], "golds": list(_golds(q)),
                          "off_docs": off_docs, "on_docs": on_docs})
        print(f"  [{setname}] retrieved {len([c for c in cache if c['set']==setname])}", flush=True)

    # ---- FASE B: generación (Ollama carga 9B una vez) ----
    print("=== FASE B: generación cita_ok ===", flush=True)
    agg = {}
    detail = []
    for c in cache:
        golds = {tuple(g) for g in c["golds"]}
        a = agg.setdefault(c["set"], {"n": 0, "off": 0, "on": 0})
        a["n"] += 1
        ro = generate_answer(c["q"], c["off_docs"], llm=llm)
        rn = generate_answer(c["q"], c["on_docs"], llm=llm)
        ok_off = _cited(extract_citations(ro["text"]), golds) and REFUSAL_TEXT.lower() not in ro["text"].lower()
        ok_on = _cited(extract_citations(rn["text"]), golds) and REFUSAL_TEXT.lower() not in rn["text"].lower()
        a["off"] += ok_off; a["on"] += ok_on
        detail.append({"set": c["set"], "q": c["q"][:60], "gold": sorted(f"{n}/{ar}" for n, ar in golds),
                       "off_ok": ok_off, "on_ok": ok_on})
        print(f"[{c['set']}] off={a['off']} on={a['on']} n={a['n']} | {c['q'][:32]}", flush=True)

    _dim = int(sys.argv[2]) if len(sys.argv) > 2 else 2560
    (OUTDIR / f"result-{_dim}.json").write_text(json.dumps({"top_k": top_k, "dim": _dim, "agg": agg, "detail": detail}, ensure_ascii=False, indent=2))
    print("\n=== VEREDICTO cita_ok (SimpleRetriever, 0.6B vs 4B) ===", flush=True)
    for s, a in agg.items():
        d = a["on"] - a["off"]
        print(f"  {s:10s} n={a['n']:2d}  OFF={a['off']:2d}  ON={a['on']:2d}  ({'+' if d>=0 else ''}{d})", flush=True)


if __name__ == "__main__":
    main()
