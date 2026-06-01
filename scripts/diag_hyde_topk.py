"""¿A qué top_k entra el gold de las situacionales con HyDE ON?

El A/B mostró que HyDE mete el gold al pool@20 pero a top_k=5 no llega (queda
rango 6-20, IdentityReranker no lo asciende). Mido gold∈pool a top_k 5/10/15/20
con HyDE ON, sobre las situacionales (indep_complex) que el router manda a
simple. Dice si subir top_k (lever barato) destapa la clase.
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
KS = [5, 10, 15, 20]


def _rank_of(docs, norma, art):
    ta = _normalize_art(str(art))
    for i, d in enumerate(docs):
        if str(d.get("id_norma")) == str(norma) and _normalize_art(str(d.get("articulo_numero"))) == ta:
            return i + 1
    return None


def main():
    rows = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["category"] == "indep_complex"]
    router = AdaptiveRouter(); router.train_default()

    e = Qwen3Embedder(device="cpu")
    r = Qwen3Reranker(device="cpu")
    store = PostgresStore()
    llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=50, top_vector=50, llm=llm)

    cfg.settings.hyde_in_simple = True
    counts = {k: 0 for k in KS}
    n = 0
    print("== situacionales simple-branch, HyDE ON, rango del gold ==\n")
    for q in rows:
        if router.classify(q["query"]) != "simple":
            continue
        n += 1
        gold = (str(q["expected_norma"]), str(q["expected_articulo"]))
        docs = retr.retrieve(q["query"], top_k=max(KS))
        rank = _rank_of(docs, *gold)
        for k in KS:
            if rank and rank <= k:
                counts[k] += 1
        print(f"gold={gold[0]}/{gold[1]:7s} rank={rank}  {q['query'][:60]}")
    cfg.settings.hyde_in_simple = False
    print(f"\n== gold∈top_k (HyDE ON, n={n} situacionales simple-branch) ==")
    for k in KS:
        print(f"  top_k={k:2d}: {counts[k]}/{n}")


if __name__ == "__main__":
    main()
