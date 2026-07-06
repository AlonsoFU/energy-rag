"""Bake-off de EMBEDDERS (3090). Screen retrieval-only EN MEMORIA (sin tocar columnas DB):
embebe los 3907 fragmentos con cada modelo, embebe las queries, mide rank del gold.

Mide coloquial (frente) + dev (no romper) → gold∈top5 / top10 por set. Compara contra el 4B
campeón. Cubre HF (e5, gte, jina, snowflake, gte-Qwen2-7B, e5-mistral-7b) y Ollama (qwen3-emb).

Cada familia tiene su convención de prefijo (e5: 'query:'/'passage:'; gte-Qwen2/e5-mistral:
instruct en la query; jina/gte-base: sin prefijo). Se aplica por modelo.

Uso: PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_emb_bakeoff [modelo1 modelo2 ...]
"""
import json, sys, os, math, time, urllib.request
from pathlib import Path
import numpy as np
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

OUTDIR = Path("data/eval/results/emb_bakeoff")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl")]

# modelo -> (loader, query_prefix, doc_prefix). loader: 'st'|'ollama'
MODELS = {
    "qwen3-emb-0.6b(ollama)":    ("ollama:qwen3-embedding:0.6b", "", ""),
    "qwen3-emb-4b(ollama)":      ("ollama:qwen3-embedding:4b", "", ""),
    "qwen3-emb-8b(ollama)":      ("ollama:qwen3-embedding:8b", "", ""),
    "e5-large":                  ("st:intfloat/multilingual-e5-large", "query: ", "passage: "),
    "e5-large-instruct":         ("st:intfloat/multilingual-e5-large-instruct", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "gte-multilingual-base":     ("st:Alibaba-NLP/gte-multilingual-base", "", ""),
    "jina-v3":                   ("st:jinaai/jina-embeddings-v3", "", ""),
    "snowflake-arctic-l-v2":     ("st:Snowflake/snowflake-arctic-embed-l-v2.0", "query: ", ""),
    "gte-Qwen2-7B":              ("st:Alibaba-NLP/gte-Qwen2-7B-instruct", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "e5-mistral-7b":             ("st:intfloat/e5-mistral-7b-instruct", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    # --- GRUPO GRANDE/MULTILINGÜE (2026-07-03) ---
    "bge-m3":                    ("st:BAAI/bge-m3", "", ""),
    "bge-multiling-gemma2":      ("st:BAAI/bge-multilingual-gemma2", "<instruct>Recupera el artículo legal relevante\n<query>", ""),
    "sfr-mistral-7b":            ("st:Salesforce/SFR-Embedding-Mistral", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "sfr-2r-7b":                 ("st:Salesforce/SFR-Embedding-2_R", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "nv-embed-v2-7b":            ("st:nvidia/NV-Embed-v2", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "linq-mistral-7b":           ("st:Linq-AI-Research/Linq-Embed-Mistral", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "kalm-multiling-v1.5":       ("st:HIT-TMG/KaLM-embedding-multilingual-mini-instruct-v1.5", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "mpnet-multiling":           ("st:sentence-transformers/paraphrase-multilingual-mpnet-base-v2", "", ""),
    "me5-large-instruct":        ("st:intfloat/multilingual-e5-large-instruct", "Instruct: Recupera el artículo legal relevante\nQuery: ", ""),
    "granite-278m-multiling":    ("st:ibm-granite/granite-embedding-278m-multilingual", "", ""),
    "arctic-m-v2":               ("st:Snowflake/snowflake-arctic-embed-m-v2.0", "query: ", ""),
    "bge-gemma2-embed-gguf":     ("ollama:bge-gemma2-embed", "", ""),
}


def load_frags():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT f.id, f.text, f.contextual_text, a.id_norma, a.numero
                       FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id""")
        rows = cur.fetchall()
    keys = [(r["id_norma"], _normalize_art(str(r["numero"]))) for r in rows]
    texts = [(r["contextual_text"] or r["text"]) for r in rows]
    return keys, texts


def load_queries():
    out = []
    for setname, path in SETS:
        for l in Path(path).read_text().splitlines():
            if not l.strip():
                continue
            q = json.loads(l)
            if q.get("expected_norma") is None:
                continue
            golds = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
            for g in q.get("also_gold") or []:
                n, a = str(g).split("/", 1); golds.add((n, _normalize_art(a)))
            out.append((setname, q["query"], golds))
    return out


def ollama_embed_batch(model, texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        d = json.dumps({"model": model, "input": texts[i:i+bs]}).encode()
        r = urllib.request.Request("http://localhost:11434/api/embed", data=d, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=300) as x:
            out.extend(json.loads(x.read())["embeddings"])
    return np.array(out, dtype=np.float32)


def encode(spec, q_prefix, d_prefix, texts, queries):
    kind, name = spec.split(":", 1)
    if kind == "ollama":
        dv = ollama_embed_batch(name, [d_prefix + t for t in texts])
        qv = ollama_embed_batch(name, [q_prefix + t for t in queries])
    else:
        from sentence_transformers import SentenceTransformer
        import torch
        dev = os.environ.get("BGE_DEVICE", "cuda")
        mk = {"torch_dtype": torch.float16} if os.environ.get("EMB_FP16", "1") == "1" else {}
        if os.environ.get("EMB_LOWMEM", "1") == "1":
            mk["low_cpu_mem_usage"] = True  # stream shards → baja pico RAM (9B en 14GB)
        try:
            m = SentenceTransformer(name, device=dev, trust_remote_code=True, model_kwargs=mk)
        except Exception:
            m = SentenceTransformer(name, device=dev, trust_remote_code=True)
        m.max_seq_length = min(getattr(m, "max_seq_length", 512) or 512, 512)
        dv = m.encode([d_prefix + t for t in texts], normalize_embeddings=True, batch_size=32, show_progress_bar=False)
        qv = m.encode([q_prefix + t for t in queries], normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        del m
        import torch, gc; gc.collect(); torch.cuda.empty_cache()
    # normaliza (ollama no garantiza norma 1)
    dv = dv / (np.linalg.norm(dv, axis=1, keepdims=True) + 1e-9)
    qv = qv / (np.linalg.norm(qv, axis=1, keepdims=True) + 1e-9)
    return dv, qv


def gold_rank(sims, keys, gold, topn=50):
    order = np.argsort(-sims)[:topn]
    seen, rank = set(), 0
    for idx in order:
        k = keys[idx]
        if k in seen:
            continue
        seen.add(k); rank += 1
        if k in gold:
            return rank
    return None


def main():
    names = sys.argv[1:] or list(MODELS.keys())
    OUTDIR.mkdir(parents=True, exist_ok=True)
    keys, texts = load_frags()
    queries = load_queries()
    qtexts = [q for _, q, _ in queries]
    print(f"corpus={len(texts)} queries={len(queries)}", flush=True)
    res = {}
    rj = OUTDIR / "result.json"
    if rj.exists():
        res = json.loads(rj.read_text())
    for nm in names:
        if nm in res:
            print(f"SKIP {nm} (hecho)", flush=True); continue
        spec, qp, dp = MODELS[nm]
        t0 = time.time()
        try:
            dv, qv = encode(spec, qp, dp, texts, qtexts)
        except Exception as ex:
            print(f"FAIL {nm}: {str(ex)[:100]}", flush=True); continue
        agg = {}
        for (setname, _, gold), qrow in zip(queries, qv):
            sims = dv @ qrow
            r = gold_rank(sims, keys, gold)
            a = agg.setdefault(setname, {"n": 0, "top5": 0, "top10": 0})
            a["n"] += 1; a["top5"] += (r is not None and r <= 5); a["top10"] += (r is not None and r <= 10)
        res[nm] = {"agg": agg, "secs": round(time.time()-t0)}
        rj.write_text(json.dumps(res, ensure_ascii=False, indent=2))
        print(f"{nm}: " + " ".join(f"{s} top5={a['top5']}/{a['n']} top10={a['top10']}" for s, a in agg.items()) + f"  ({res[nm]['secs']}s)", flush=True)
    print("\n=== BAKE-OFF EMBEDDERS (gold∈topN) ===", flush=True)
    print(f"{'modelo':24s} {'cx_t5':>6s} {'cx_t10':>7s} {'dev_t5':>7s} {'dev_t10':>8s}", flush=True)
    for nm in names:
        if nm not in res: continue
        a = res[nm]["agg"]; cx = a.get("coloquial", {}); dv = a.get("dev", {})
        print(f"{nm:24s} {cx.get('top5',0):>6d} {cx.get('top10',0):>7d} {dv.get('top5',0):>7d} {dv.get('top10',0):>8d}", flush=True)


if __name__ == "__main__":
    main()
