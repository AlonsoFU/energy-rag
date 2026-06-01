"""A/B barato (retrieval-only) del flag hyde_in_simple, aislando el cambio.

Mi flag solo afecta queries que el router manda a SIMPLE (las de complejo ya
expanden). Así que clasifico las 49q, me quedo con las simple, y mido
gold∈pool@5 con el flag OFF vs ON, por categoría. Confirma que HyDE sube la
clase situacional SIN regresar la definicional, antes de gastar la eval de
generación. Embedder en CPU para no competir con el 9b (HyDE) en la GPU.
"""
import json
from pathlib import Path

from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.routing.adaptive import AdaptiveRouter
from src.core import config as cfg
from src.pipelines.grounding import _normalize_art

EVAL = Path("data/eval/queries_independent.jsonl")
TOP_K = 5  # top_k de PRODUCCIÓN (no 20)


def _in_pool(docs, norma, art):
    ta = _normalize_art(str(art))
    return any(str(d.get("id_norma")) == str(norma)
              and _normalize_art(str(d.get("articulo_numero"))) == ta for d in docs)


def main():
    rows = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("expected_norma")]  # positivas

    router = AdaptiveRouter(); router.train_default()
    simple_rows = [r for r in rows if router.classify(r["query"]) == "simple"]

    e = Qwen3Embedder(device="cpu")
    r = Qwen3Reranker(device="cpu")
    store = PostgresStore()
    llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, llm=llm)

    from collections import defaultdict
    agg = defaultdict(lambda: {"n": 0, "off": 0, "on": 0})
    print(f"== A/B hyde_in_simple sobre {len(simple_rows)} queries simple-branch ==\n")
    for q in simple_rows:
        gold = (str(q["expected_norma"]), str(q["expected_articulo"]))
        cat = q["category"]
        cfg.settings.hyde_in_simple = False
        off = _in_pool(retr.retrieve(q["query"], top_k=TOP_K), *gold)
        cfg.settings.hyde_in_simple = True
        on = _in_pool(retr.retrieve(q["query"], top_k=TOP_K), *gold)
        cfg.settings.hyde_in_simple = False
        a = agg[cat]; a["n"] += 1; a["off"] += off; a["on"] += on
        flag = "↑" if on and not off else ("↓" if off and not on else " ")
        print(f"[{flag}] {cat:20s} gold={gold[0]}/{gold[1]:6s} off={'Y' if off else 'N'} on={'Y' if on else 'N'}  {q['query'][:55]}")

    print(f"\n== gold∈pool@{TOP_K} por categoría (solo simple-branch) ==")
    tn = toff = ton = 0
    for cat, a in sorted(agg.items()):
        print(f"  {cat:22s} off={a['off']}/{a['n']}  on={a['on']}/{a['n']}")
        tn += a["n"]; toff += a["off"]; ton += a["on"]
    print(f"  {'TOTAL':22s} off={toff}/{tn}  on={ton}/{tn}  (Δ={ton-toff:+d})")


if __name__ == "__main__":
    main()
