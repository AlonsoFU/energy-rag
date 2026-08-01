"""Gen eval del alias_union (Exp #2): ¿el rescate de retrieval (87/118/212 a top-10 en el
screen) CONVIERTE a cita_ok? Aísla el efecto del alias SOBRE el 4B-1024.

OFF = 4B-1024 dense (sin alias) | ON = 4B-1024 dense + alias_union.
Ambos embed_4b_dense=True, dim=1024. Mide coloquial/dev/holdout. SimpleRetriever (limpio,
sin 9B en retrieval). Dos fases para evitar swap Ollama 4B↔9B.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_alias_gen [top_k]
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

OUTDIR = Path("data/eval/results/alias_gen")
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
    cfg.settings.embed_4b_dense = True
    cfg.settings.embed_4b_dim = 1024

    # ---- FASE A: retrieval (Ollama=4B). OFF=sin alias, ON=alias_union ----
    print("=== FASE A: retrieval 4B-1024  OFF(sin alias) + ON(alias_union) ===", flush=True)
    cache = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        for q in rows:
            cfg.settings.alias_union = False
            off_docs = retr.retrieve(q["query"], top_k=top_k)
            cfg.settings.alias_union = True
            on_docs = retr.retrieve(q["query"], top_k=top_k)
            cfg.settings.alias_union = False
            cache.append({"set": setname, "q": q["query"], "golds": list(_golds(q)),
                          "off_docs": off_docs, "on_docs": on_docs})
        print(f"  [{setname}] retrieved {len([c for c in cache if c['set']==setname])}", flush=True)
    cfg.settings.embed_4b_dense = False  # libera para que el 9B entre a GPU

    # ---- FASE B: generación (Ollama=9B) ----
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

    (OUTDIR / "result.json").write_text(json.dumps({"top_k": top_k, "agg": agg, "detail": detail}, ensure_ascii=False, indent=2))
    print("\n=== VEREDICTO cita_ok (4B-1024: sin alias vs alias_union) ===", flush=True)
    for s, a in agg.items():
        d = a["on"] - a["off"]
        print(f"  {s:10s} n={a['n']:2d}  OFF={a['off']:2d}  ON={a['on']:2d}  ({'+' if d>=0 else ''}{d})", flush=True)


if __name__ == "__main__":
    main()
