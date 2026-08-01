"""Generation eval del Exp #4 (concept_inference): ¿el +retrieval convierte a cita_ok?

El screen retrieval-only mostró coloquial gold∈top10 28→31 (+3), dev 36→40 (+4), sin
regresión, PERO top5 +0 → el gold entra al pool, no al top-5. Por eso este eval usa
top_k=10 y la pipeline de PRODUCCIÓN (AdaptiveRetriever → complejo para coloquial),
para medir si el gold recién metido al pool se traduce en la cita correcta.

Corre OFF y ON por query (concept_inference cambia el retrieval → hay que recuperar+
generar 2 veces). coloquial=target; dev+holdout=no-regresión.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_concept_inference_gen [top_k]
Solo con GPU+RAM libres. BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu USE_BGE_RERANKER=1.
"""
import json, sys
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
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/concept_inference_gen")
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
    router = AdaptiveRouter(); router.train_default()
    pool = cfg.settings.retrieval_pool_depth
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"=== concept_inference GEN === top_k={top_k}", flush=True)

    def run_one(q):
        branch, docs = adaptive.retrieve(q["query"], top_k=top_k)
        res = generate_answer(q["query"], docs, llm=llm)
        cits = extract_citations(res["text"])
        refused = REFUSAL_TEXT.lower() in res["text"].lower()
        return cits, refused

    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        agg = {"n": 0, "off": 0, "on": 0}
        detail = []
        for q in rows:
            golds = _golds(q); agg["n"] += 1
            cfg.settings.concept_inference = False
            co, ro = run_one(q); ok_off = _cited(co, golds)
            cfg.settings.concept_inference = True
            cn, rn = run_one(q); ok_on = _cited(cn, golds)
            cfg.settings.concept_inference = False
            agg["off"] += ok_off; agg["on"] += ok_on
            detail.append({"q": q["query"][:60], "gold": sorted(golds),
                           "off_ok": ok_off, "on_ok": ok_on,
                           "off_cits": [f"{n}/{a}" for n, a in co],
                           "on_cits": [f"{n}/{a}" for n, a in cn]})
            print(f"[{setname}] n={agg['n']} off={agg['off']} on={agg['on']} | {q['query'][:34]}", flush=True)
        out = {"set": setname, "top_k": top_k, "agg": agg, "detail": detail}
        (OUTDIR / f"{setname}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
        d = agg["on"] - agg["off"]
        print(f"\n=== {setname} n={agg['n']}: cita_ok OFF={agg['off']} ON={agg['on']} ({'+' if d>=0 else ''}{d}) ===\n", flush=True)


if __name__ == "__main__":
    main()
