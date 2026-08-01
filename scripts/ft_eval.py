"""FASE C paso 3 — eval pure-vector: embedder FT vs base, gold-article∈top10.

Embebe TODOS los artículos (texto) con cada modelo, embebe las queries de cada set,
y mide si el ARTÍCULO gold cae en top10 por coseno. Aísla el aporte del embedder
(sin BM25/rerank). target = coloquial_v2 (held-out: sus artículos no se entrenaron).
no-regresión = independent (dev), holdout, extreme.

Uso: HF_HUB_OFFLINE=1 EMBEDDER_DEVICE=cuda ./venv-gpu/bin/python -m scripts.ft_eval
"""
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from src.storage.connection import with_connection

import os
BASE = "Qwen/Qwen3-Embedding-0.6B"
FT = os.environ.get("FT_EVAL_PATH", "models/qwen3-ft-coloquial")
SETS = {
    "coloquial(target)": ("data/eval/queries_coloquial_v2.jsonl", {"cx_coloquial"}),
    "dev(no-reg)": ("data/eval/queries_independent.jsonl", None),
    "holdout(no-reg)": ("data/eval/queries_holdout.jsonl", None),
    "extreme(no-reg)": ("data/eval/queries_extreme.jsonl", None),
}


def load_arts():
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_norma, numero, texto FROM articulos WHERE length(texto)>40")
        rows = cur.fetchall()
    keys = [(str(n), str(a)) for n, a, _ in rows]
    texts = [t for _, _, t in rows]
    return keys, texts


def load_set(path, cats):
    out = []
    for l in open(path):
        d = json.loads(l)
        if not d.get("expected_norma"):
            continue
        if cats and d.get("category") not in cats:
            continue
        golds = {(str(d["expected_norma"]), str(d["expected_articulo"]))}
        for g in d.get("also_gold") or []:
            n, a = str(g).split("/", 1); golds.add((n, a))
        out.append((d["query"], golds))
    return out


def emb(model, texts, bs=16):
    return model.encode(texts, batch_size=bs, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True)


def eval_model(tag, model_path, keys, art_texts, sets):
    import torch
    m = SentenceTransformer(model_path, device="cuda", trust_remote_code=True)
    m.max_seq_length = 320
    A = emb(m, art_texts)  # (N_art, d)
    idx_of = {k: i for i, k in enumerate(keys)}
    print(f"\n=== {tag} ===")
    for name, items in sets.items():
        qs = [q for q, _ in items]
        Q = emb(m, qs)  # (n, d)
        sims = Q @ A.T  # cosine (normalized)
        top = np.argsort(-sims, axis=1)[:, :10]
        hit = 0
        for i, (_, golds) in enumerate(items):
            gidx = {idx_of[g] for g in golds if g in idx_of}
            if gidx & set(top[i].tolist()):
                hit += 1
        print(f"  {name:20s} gold∈top10 = {hit}/{len(items)}")
    del m, A
    torch.cuda.empty_cache()


def main():
    keys, art_texts = load_arts()
    print(f"artículos indexados: {len(keys)}")
    sets = {name: load_set(p, c) for name, (p, c) in SETS.items()}
    eval_model("BASE Qwen3-0.6B", BASE, keys, art_texts, sets)
    eval_model("FT coloquial", FT, keys, art_texts, sets)


if __name__ == "__main__":
    main()
