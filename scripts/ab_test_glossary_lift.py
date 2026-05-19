"""A/B test: measure glossary lift on alias queries WITHOUT modifying DB.

Runs the same 15 alias queries twice through SimpleRetriever:
  - Pass A (baseline): query_concepts=[] → skips graph_boost
  - Pass B (with-glossary): query_concepts=None → auto-detect aliases → graph_boost

For each query, reports:
  - Did the same docs come back in different order?
  - Are there new docs in B that weren't in A's top-K?
  - Did the boost change the top-1?

This is the right way to measure the glossary's contribution: it isolates
the alias→graph_boost pathway without depending on hand-labeled
expected_norma values (which are unreliable, see eval at 19:33 today).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.routing.adaptive import AdaptiveRouter  # noqa: F401  (loaded indirectly)
from src.pipelines.retrieve import SimpleRetriever
from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.components.vectorstore import PostgresStore

ROOT = Path(__file__).resolve().parent.parent
EVAL_PATH = ROOT / "data" / "eval" / "queries_aliases.jsonl"


def load_queries():
    return [
        json.loads(line)
        for line in EVAL_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def doc_id(d):
    return f"{d.get('id_norma','?')}/{d.get('articulo_numero','?')}"


def main():
    store = PostgresStore()
    embedder = Qwen3Embedder()
    reranker = Qwen3Reranker()
    retriever = SimpleRetriever(store, embedder, reranker)

    queries = load_queries()
    print(f"Running A/B over {len(queries)} alias queries\n")

    results = []
    for q in queries:
        text = q["query"]
        # Pass A: NO glossary (force empty concepts → skip graph_boost)
        a_docs = retriever.retrieve(text, top_k=10, query_concepts=[])
        # Pass B: WITH glossary (auto-detect → graph_boost active)
        b_docs = retriever.retrieve(text, top_k=10, query_concepts=None)

        a_ids = [doc_id(d) for d in a_docs]
        b_ids = [doc_id(d) for d in b_docs]
        same_top1 = a_ids[:1] == b_ids[:1]
        same_set = set(a_ids) == set(b_ids)
        new_in_b = [x for x in b_ids if x not in a_ids]
        only_in_a = [x for x in a_ids if x not in b_ids]

        results.append({
            "query": text,
            "top1_a": a_ids[0] if a_ids else None,
            "top1_b": b_ids[0] if b_ids else None,
            "top1_changed": not same_top1,
            "set_changed": not same_set,
            "new_in_b": new_in_b,
            "only_in_a": only_in_a,
        })
        flag = "→reordered" if same_set and not same_top1 else (
            "→set diff" if not same_set else "=no change"
        )
        print(f"{text[:35]:<35} A={a_ids[0]:<22} B={b_ids[0]:<22} {flag}")
        if not same_set:
            for x in new_in_b:
                print(f"    +B: {x}")
            for x in only_in_a:
                print(f"    -A: {x}")

    # Summary
    n = len(results)
    n_top1_changed = sum(1 for r in results if r["top1_changed"])
    n_set_changed = sum(1 for r in results if r["set_changed"])
    print(f"\n=== Summary ===")
    print(f"Top-1 changed by glossary: {n_top1_changed}/{n}")
    print(f"Set of top-10 changed:     {n_set_changed}/{n}")

    out_path = ROOT / "data" / "eval" / "ab_glossary_lift.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
