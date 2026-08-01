"""Screen 8B vs 4B vs 0.6B (vector-only gold∈top-N). ¿El 8B aporta sobre el 4B?
Dos fases para evitar swap Ollama 4b↔8b: embebe TODAS las queries con 4b, luego con 8b.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_8b_screen
"""
import json, urllib.request
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl"),
        ("holdout", "data/eval/queries_holdout.jsonl")]
TOPS = [5, 10, 20]


def embed(model, text):
    data = json.dumps({"model": model, "input": [text]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/embed", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["embeddings"][0]


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
    allq = []
    for setname, path in SETS:
        for l in Path(path).read_text().splitlines():
            if not l.strip():
                continue
            q = json.loads(l)
            if q.get("expected_norma") is not None:
                allq.append((setname, q))
    print(f"=== screen 8B vs 4B vs 0.6B, {len(allq)} queries ===", flush=True)
    # Fase 1: 0.6B (CPU) + 4B (Ollama)
    e4 = {}
    for i, (s, q) in enumerate(allq):
        e4[i] = embed("qwen3-embedding:4b", q["query"])
    print("4B embeds listos", flush=True)
    # Fase 2: 8B (Ollama, swap una vez)
    e8 = {}
    for i, (s, q) in enumerate(allq):
        e8[i] = embed("qwen3-embedding:8b", q["query"])
    print("8B embeds listos", flush=True)

    agg = {}
    for i, (s, q) in enumerate(allq):
        g = _golds(q)
        a = agg.setdefault(s, {f"{m}@{n}": 0 for m in ("06", "4b", "8b") for n in TOPS})
        d06 = knn("embedding", e06.embed([q["query"]])[0])
        d4 = knn("embedding_4b", e4[i])
        d8 = knn("embedding_8b", e8[i])
        for n in TOPS:
            a[f"06@{n}"] += _hit(d06, g, n)
            a[f"4b@{n}"] += _hit(d4, g, n)
            a[f"8b@{n}"] += _hit(d8, g, n)
    for s, a in agg.items():
        print(f"\n=== {s} (gold∈top-N) ===", flush=True)
        for n in TOPS:
            print(f"  top{n:>2}: 0.6B={a[f'06@{n}']:2d}  4B={a[f'4b@{n}']:2d}  8B={a[f'8b@{n}']:2d}", flush=True)


if __name__ == "__main__":
    main()
