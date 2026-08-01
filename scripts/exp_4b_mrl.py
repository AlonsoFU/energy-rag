"""Validación MRL: ¿el win del 4B (2560-dim) sobrevive truncado a 1024-dim?

1024-dim es indexable con HNSW (pgvector >2000 no indexa) → escala a corpus grande.
Compara gold∈top-N vector-only: 0.6B vs 4B-2560 (seq-scan) vs 4B-1024 (HNSW, MRL prefix).
Query 4B truncada a 1024 + renormalizada para igualar el corpus.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_4b_mrl
"""
import json, urllib.request, math
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl"),
        ("holdout", "data/eval/queries_holdout.jsonl")]
TOPS = [5, 10, 20]


def embed_4b(text):
    data = json.dumps({"model": "qwen3-embedding:4b", "input": [text]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/embed", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embeddings"][0]


def trunc1024(v):
    s = v[:1024]
    n = math.sqrt(sum(x*x for x in s)) or 1.0
    return [x/n for x in s]


def knn(col, emb, top_k=20):
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT a.id_norma, a.numero AS articulo_numero
            FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id
            WHERE f.{col} IS NOT NULL ORDER BY f.{col} <=> %s::vector LIMIT %s""", (str(emb), top_k))
        return cur.fetchall()


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _hit(docs, golds, n):
    return any((str(d["id_norma"]), _normalize_art(str(d["articulo_numero"]))) in golds for d in docs[:n])


def main():
    e06 = Qwen3Embedder()
    print("=== MRL screen: 0.6B vs 4B-2560 vs 4B-1024 (vector-only) ===", flush=True)
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        agg = {f"{m}@{n}": 0 for m in ("06", "2560", "1024") for n in TOPS}
        for q in rows:
            g = _golds(q)
            v4 = embed_4b(q["query"])
            d06 = knn("embedding", e06.embed([q["query"]])[0])
            d25 = knn("embedding_4b", v4)
            d10 = knn("embedding_4b_1024", trunc1024(v4))
            for n in TOPS:
                agg[f"06@{n}"] += _hit(d06, g, n)
                agg[f"2560@{n}"] += _hit(d25, g, n)
                agg[f"1024@{n}"] += _hit(d10, g, n)
        print(f"\n=== {setname} n={len(rows)} (gold∈top-N) ===", flush=True)
        for n in TOPS:
            print(f"  top{n:>2}: 0.6B={agg[f'06@{n}']:2d}  4B-2560={agg[f'2560@{n}']:2d}  "
                  f"4B-1024={agg[f'1024@{n}']:2d}", flush=True)


if __name__ == "__main__":
    main()
