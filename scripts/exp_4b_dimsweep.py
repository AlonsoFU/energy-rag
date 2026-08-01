"""Barrido de dim MRL: ¿cuál es el dim mínimo que conserva el win del 4B?
Vector-only gold∈top-N: 0.6B vs 4B-512 vs 4B-1024 vs 4B-2560. 512/1024 indexables HNSW.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_4b_dimsweep
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


def trunc(v, d):
    s = v[:d]; n = math.sqrt(sum(x*x for x in s)) or 1.0
    return [x/n for x in s]


def knn(col, emb):
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT a.id_norma, a.numero AS articulo_numero FROM fragmentos f
            JOIN articulos a ON a.id=f.articulo_id WHERE f.{col} IS NOT NULL
            ORDER BY f.{col} <=> %s::vector LIMIT 20""", (str(emb),))
        return cur.fetchall()


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _hit(docs, g, n):
    return any((str(d["id_norma"]), _normalize_art(str(d["articulo_numero"]))) in g for d in docs[:n])


def main():
    e06 = Qwen3Embedder()
    print("=== barrido dim MRL: 0.6B vs 4B 512/1024/2560 (vector-only) ===", flush=True)
    cols = {"06": ("embedding", None), "512": ("embedding_4b_512", 512),
            "1024": ("embedding_4b_1024", 1024), "2560": ("embedding_4b", 2560)}
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        agg = {f"{m}@{n}": 0 for m in cols for n in TOPS}
        for q in rows:
            g = _golds(q); v4 = embed_4b(q["query"]); v06 = e06.embed([q["query"]])[0]
            for m, (col, d) in cols.items():
                emb = v06 if m == "06" else (v4 if d == 2560 else trunc(v4, d))
                docs = knn(col, emb)
                for n in TOPS:
                    agg[f"{m}@{n}"] += _hit(docs, g, n)
        print(f"\n=== {setname} n={len(rows)} (gold∈top-N) ===", flush=True)
        for n in TOPS:
            print(f"  top{n:>2}: 0.6B={agg[f'06@{n}']:2d}  512={agg[f'512@{n}']:2d}  "
                  f"1024={agg[f'1024@{n}']:2d}  2560={agg[f'2560@{n}']:2d}", flush=True)


if __name__ == "__main__":
    main()
