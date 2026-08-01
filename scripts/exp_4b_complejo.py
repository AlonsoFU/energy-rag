"""Gen eval del 4B en la ruta de PRODUCCIÓN (AdaptiveRetriever → complejo para coloquial).

El eval anterior (exp_4b_gen) usó SimpleRetriever (limpio pero no producción). Este usa el
router real: coloquial rutea a complejo (expansión LLM con el 9B). Para evitar swap 4b↔9b,
el embed 4B corre en CPU (embed_4b_cpu, Ollama num_gpu=0); el 9B queda en GPU.

OFF = 0.6B dense | ON = 4B-1024 dense (CPU). cita_ok coloquial/dev/holdout.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_4b_complejo [top_k]
"""
import json, sys
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/emb4b_complejo")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl"),
        ("holdout", "data/eval/queries_holdout.jsonl")]


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
    router = AdaptiveRouter(); router.train_default()
    pool = cfg.settings.retrieval_pool_depth
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)
    cfg.settings.embed_4b_cpu = True   # embed 4B en CPU → no swap con el 9B
    cfg.settings.embed_4b_dim = 1024
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"=== 4B en COMPLEJO (producción) top_k={top_k}, embed 4B en CPU ===", flush=True)
    agg = {}
    detail = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        a = agg.setdefault(setname, {"n": 0, "off": 0, "on": 0})
        for q in rows:
            golds = _golds(q); a["n"] += 1
            cfg.settings.embed_4b_dense = False
            _, doff = adaptive.retrieve(q["query"], top_k=top_k)
            ro = generate_answer(q["query"], doff, llm=llm)
            cfg.settings.embed_4b_dense = True
            _, don = adaptive.retrieve(q["query"], top_k=top_k)
            rn = generate_answer(q["query"], don, llm=llm)
            cfg.settings.embed_4b_dense = False
            ok_off = _cited(extract_citations(ro["text"]), golds) and REFUSAL_TEXT.lower() not in ro["text"].lower()
            ok_on = _cited(extract_citations(rn["text"]), golds) and REFUSAL_TEXT.lower() not in rn["text"].lower()
            a["off"] += ok_off; a["on"] += ok_on
            detail.append({"set": setname, "q": q["query"][:60], "off_ok": ok_off, "on_ok": ok_on})
            print(f"[{setname}] off={a['off']} on={a['on']} n={a['n']} | {q['query'][:30]}", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"top_k": top_k, "agg": agg, "detail": detail}, ensure_ascii=False, indent=2))
    print("\n=== VEREDICTO 4B en complejo (cita_ok) ===", flush=True)
    for s, a in agg.items():
        print(f"  {s:10s} OFF={a['off']:2d} ON={a['on']:2d} ({a['on']-a['off']:+d})", flush=True)


if __name__ == "__main__":
    main()
