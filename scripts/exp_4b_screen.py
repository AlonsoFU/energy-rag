"""SCREEN: embedder Qwen3-Embedding-4B (GGUF Ollama) vs 0.6B (actual), vector-only.

Aísla el EMBEDDER: embebe la query con cada uno, KNN puro (sin BM25/rerank), mide
gold∈top-N a nivel artículo. ¿El 4B grande mete el gold coloquial al pool donde el
0.6B no? Es el único salto real no probado (antes parecía bloqueado por hardware;
el GGUF 4-bit de Ollama SÍ cabe en la GTX 1080).

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_4b_screen
Requiere fragmentos.embedding_4b poblada (scripts.embed_4b) + Ollama qwen3-embedding:4b.
"""
import json, urllib.request
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.vectorstore import PostgresStore
from src.pipelines.grounding import _normalize_art

SETS = [
    ("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
    ("dev",       "data/eval/queries_independent.jsonl"),
    ("holdout",   "data/eval/queries_holdout.jsonl"),
]
TOPS = [5, 10, 20]
OUTDIR = Path("data/eval/results/emb4b")


def embed_4b(text):
    data = json.dumps({"model": "qwen3-embedding:4b", "input": [text]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/embed", data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["embeddings"][0]


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _hit(docs, golds, n):
    return any((str(d["id_norma"]), _normalize_art(str(d["articulo_numero"]))) in golds
               for d in docs[:n])


def main():
    e06 = Qwen3Embedder()
    store = PostgresStore()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print("=== SCREEN emb 4B vs 0.6B (vector-only KNN) ===", flush=True)
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        agg = {f"{m}@{n}": 0 for m in ("06", "4b") for n in TOPS}
        detail = []
        for q in rows:
            golds = _golds(q)
            d06 = store.search_vector(e06.embed([q["query"]])[0], top_k=max(TOPS))
            d4b = store.search_vector_4b(embed_4b(q["query"]), top_k=max(TOPS))
            row = {"q": q["query"][:55], "gold": sorted(golds), "06": {}, "4b": {}}
            for n in TOPS:
                h6 = _hit(d06, golds, n); h4 = _hit(d4b, golds, n)
                agg[f"06@{n}"] += h6; agg[f"4b@{n}"] += h4
                row["06"][n] = h6; row["4b"][n] = h4
            detail.append(row)
            print(f"[{setname}] 06@10={agg['06@10']} 4b@10={agg['4b@10']} | {q['query'][:34]}", flush=True)
        (OUTDIR / f"{setname}.json").write_text(json.dumps({"set": setname, "n": len(rows),
                                                            "agg": agg, "detail": detail}, ensure_ascii=False, indent=2))
        print(f"\n=== {setname} n={len(rows)} (vector-only gold∈top-N) ===", flush=True)
        for n in TOPS:
            d = agg[f"4b@{n}"] - agg[f"06@{n}"]
            print(f"  top{n:>2}: 0.6B={agg[f'06@{n}']:2d}  4B={agg[f'4b@{n}']:2d}  ({'+' if d>=0 else ''}{d})", flush=True)
        print("", flush=True)


if __name__ == "__main__":
    main()
