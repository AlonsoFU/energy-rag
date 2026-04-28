"""Minimal recall@k runner over a JSONL eval set.

Each JSONL line: {"query": str, "expected_norma": str, "expected_articulo": str|None}.
The retriever must return (branch, list[{"id_norma","articulo_numero",...}]).
"""
import json
from pathlib import Path


def run_deepeval(eval_file: Path | str, retriever, top_k: int = 5) -> dict:
    eval_file = Path(eval_file)
    queries = [
        json.loads(line) for line in eval_file.read_text().splitlines() if line.strip()
    ]
    hits = 0
    for q in queries:
        _, docs = retriever.retrieve(q["query"], top_k=top_k)
        norma_match = any(
            d.get("id_norma") == q.get("expected_norma")
            and (
                q.get("expected_articulo") is None
                or str(d.get("articulo_numero", "")).rstrip("°") == str(q.get("expected_articulo")).rstrip("°")
            )
            for d in docs
        )
        if norma_match:
            hits += 1
    return {
        "n_queries": len(queries),
        "recall_at_5": hits / len(queries) if queries else 0.0,
    }
