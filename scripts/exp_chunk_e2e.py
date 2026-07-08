"""Confirmación END-TO-END (cita_ok) del ganador de chunking `inciso_robust+path`.

Construye una tabla PARALELA `fragmentos_inciso` (no toca producción `fragmentos`),
corre el pipeline REAL (BM25+vector 4b-1024 + RRF + BGE rerank + gen 30b-a3b) sobre ella
y compara cita_ok vs baseline `asis`. Solo genera en queries donde el top-10 (por artículo)
DIFIERE entre inciso y asis (ahorra llamadas). El screen MIENTE → esto es lo que decide.

Uso:
  build:  HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.exp_chunk_e2e build
  eval :  HF_HUB_OFFLINE=1 BGE_DEVICE=cuda ./venv-gpu/bin/python -m scripts.exp_chunk_e2e eval <set.jsonl>
"""
import json, sys, os, urllib.request, time
from pathlib import Path
import numpy as np
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.components.vectorstore import PostgresStore
from src.components.reranker import get_reranker
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion, _length_weights
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import _normalize_art
from scripts.exp_gen_bakeoff import _ok, _golds
from scripts.exp_chunk_sweep import load_articulos, ck_inciso_robust, ctx_path

OLL = "http://localhost:11434"
GENM = "ollama/" + os.environ.get("GEN_MODEL", "qwen3:30b-a3b")
OUT = Path("data/eval/results/chunk_e2e"); OUT.mkdir(parents=True, exist_ok=True)


def emb_batch(texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        b = json.dumps({"model": "qwen3-embedding:4b", "input": texts[i:i+bs]}).encode()
        r = urllib.request.Request(OLL+"/api/embed", b, {"Content-Type": "application/json"})
        out.extend(json.loads(urllib.request.urlopen(r, timeout=600).read())["embeddings"])
    v = np.array(out, dtype=np.float32)[:, :1024]
    v = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)
    return v.tolist()


def emb_query(text):
    b = json.dumps({"model": "qwen3-embedding:4b", "input": text}).encode()
    r = urllib.request.Request(OLL+"/api/embed", b, {"Content-Type": "application/json"})
    e = json.loads(urllib.request.urlopen(r, timeout=60).read())["embeddings"][0][:1024]
    n = np.linalg.norm(e) + 1e-9
    return [x/n for x in e]


def build():
    t0 = time.time()
    # 1) tabla + filas (SIN embedding) — rápido, idempotente si ya poblada
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass('fragmentos_inciso')")
        exists = cur.fetchone()[0] is not None
        if exists:
            cur.execute("SELECT count(*) FROM fragmentos_inciso"); npop = cur.fetchone()[0]
        if not exists or npop == 0:
            cur.execute("DROP TABLE IF EXISTS fragmentos_inciso")
            cur.execute("""CREATE TABLE fragmentos_inciso (
                id bigserial PRIMARY KEY, articulo_id bigint, id_norma text, numero text,
                text text, contextual_text text, embedding_4b_1024 vector(1024),
                tsv tsvector)""")
            arts = load_articulos()
            with cur.copy("COPY fragmentos_inciso (articulo_id,id_norma,numero,text,contextual_text) FROM STDIN") as cp:
                for a in arts:
                    for frag in ck_inciso_robust(a):
                        if frag.strip():
                            cp.write_row((a["id"], a["id_norma"], str(a["numero"]), frag, ctx_path(a, frag)))
            cur.execute("UPDATE fragmentos_inciso SET tsv = to_tsvector('spanish', contextual_text)")
            conn.commit()
        cur.execute("SELECT count(*) FROM fragmentos_inciso"); N = cur.fetchone()[0]
    print(f"filas={N}, poblando embeddings (resumable)...", flush=True)
    # 2) embed por lotes con commit por lote (resumable: sigue desde NULL)
    while True:
        with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, contextual_text FROM fragmentos_inciso WHERE embedding_4b_1024 IS NULL ORDER BY id LIMIT 128")
            batch = cur.fetchall()
        if not batch:
            break
        embs = emb_batch([r["contextual_text"] for r in batch])
        with with_connection() as conn, conn.cursor() as cur:
            for r, e in zip(batch, embs):
                cur.execute("UPDATE fragmentos_inciso SET embedding_4b_1024=%s WHERE id=%s",
                            ("[" + ",".join(map(str, e)) + "]", r["id"]))
            conn.commit()
        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM fragmentos_inciso WHERE embedding_4b_1024 IS NOT NULL"); d = cur.fetchone()[0]
        print(f"  emb {d}/{N} ({time.time()-t0:.0f}s)", flush=True)
    # 3) índices (idempotente)
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("CREATE INDEX IF NOT EXISTS fi_hnsw ON fragmentos_inciso USING hnsw (embedding_4b_1024 vector_cosine_ops)")
        cur.execute("CREATE INDEX IF NOT EXISTS fi_gin ON fragmentos_inciso USING gin (tsv)")
        conn.commit()
    print(f"tabla fragmentos_inciso lista: {N} filas ({time.time()-t0:.0f}s)", flush=True)


def inciso_bm25(query, top_k=50):
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, articulo_id, text, contextual_text, id_norma,
            numero AS articulo_numero, ts_rank_cd(tsv, plainto_tsquery('spanish', %s)) AS score
            FROM fragmentos_inciso WHERE tsv @@ plainto_tsquery('spanish', %s)
            ORDER BY score DESC LIMIT %s""", (query, query, top_k))
        return cur.fetchall()


def inciso_vec(qemb, top_k=50):
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, articulo_id, text, contextual_text, id_norma,
            numero AS articulo_numero, 1-(embedding_4b_1024 <=> %s::vector) AS score
            FROM fragmentos_inciso ORDER BY embedding_4b_1024 <=> %s::vector LIMIT %s""",
                    (qemb, qemb, top_k))
        return cur.fetchall()


def pool_asis(query, store):
    bm = store.search_bm25(query, top_k=50)
    vec = store.search_vector_4b_1024(emb_query(query), top_k=50)
    return rrf_fusion([bm, vec], k=60, weights=_length_weights(query))[:50]


def pool_inciso(query):
    bm = inciso_bm25(query, 50)
    vec = inciso_vec(emb_query(query), 50)
    return rrf_fusion([bm, vec], k=60, weights=_length_weights(query))[:50]


def artset(docs):
    return {(str(d.get("id_norma")), _normalize_art(str(d.get("articulo_numero")))) for d in docs}


def eval_set(setf):
    rows = [json.loads(l) for l in open(setf) if l.strip()]
    rows = [q for q in rows if q.get("expected_norma")]
    store, RR = PostgresStore(), get_reranker()
    ck = OUT / (Path(setf).stem + "__" + os.environ.get("GEN_MODEL", "30b").replace(":", "-").replace(".", "") + ".json")
    done = json.loads(ck.read_text()) if ck.exists() else {}
    # === PASADA 1: pools + rerank (4b + BGE, sin gen) → cachea top10 docs por query ===
    poolf = OUT / (Path(setf).stem + "__pools.json")
    if poolf.exists():
        cache = json.loads(poolf.read_text())
    else:
        cache = {}
        for i, q in enumerate(rows):
            key = q["query"]
            entry = {}
            for mode, pool in [("asis", pool_asis(key, store)), ("inciso", pool_inciso(key))]:
                texts = [(d.get("contextual_text") or d.get("text") or "") for d in pool]
                ranked = RR.rerank(key, texts, top_k=10) if texts else []
                docs = [pool[j] for j, _ in ranked] if ranked else pool[:10]
                entry[mode] = [{"id_norma": d.get("id_norma"), "articulo_numero": d.get("articulo_numero"),
                                "contextual_text": d.get("contextual_text"), "text": d.get("text")} for d in docs[:10]]
            cache[key] = entry
            print(f"  pool {i+1}/{len(rows)}", flush=True)
        poolf.write_text(json.dumps(cache, ensure_ascii=False))
        print("=== pools cacheados; ahora GEN (30b) ===", flush=True)
    # === PASADA 2: gen 30b solo en queries que difieren ===
    llm = get_llm_provider()
    for i, q in enumerate(rows):
        key = q["query"]
        if key in done:
            continue
        golds = set(_golds(q))
        res = {m: cache[key][m] for m in ("asis", "inciso")}
        same = artset(res["asis"][:10]) == artset(res["inciso"][:10])
        out = {"same_top10": same}
        if same:
            # top10 idéntico por artículo → cita_ok igual en ambos → delta 0, no gastar gen
            out["asis"] = out["inciso"] = None
        else:
            for mode in ("asis", "inciso"):
                docs = res[mode]
                for dd in docs:
                    dd.setdefault("articulo_text", dd.get("contextual_text") or dd.get("text") or "")
                try:
                    out[mode] = int(_ok(generate_answer(key, docs, llm=llm, model=GENM), golds))
                except Exception as ex:
                    print(f"  {i+1} GEN-FAIL {str(ex)[:40]}", flush=True); out[mode] = 0
        done[key] = out; ck.write_text(json.dumps(done, ensure_ascii=False))
        diff = [v for v in done.values() if not v["same_top10"]]
        ca = sum(v["asis"] for v in diff); ci = sum(v["inciso"] for v in diff)
        print(f"  {i+1}/{len(rows)} same={same} asis={out['asis']} inciso={out['inciso']} | dif={len(diff)} asis={ca} inciso={ci}", flush=True)
    diff = [v for v in done.values() if not v["same_top10"]]
    ca = sum(v["asis"] for v in diff); ci = sum(v["inciso"] for v in diff)
    print(f"\n{Path(setf).stem}: en {len(diff)} queries con top10 distinto → cita_ok asis={ca} inciso={ci} (delta {ci-ca:+d}); {len(done)-len(diff)} iguales (delta 0)", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    else:
        eval_set(sys.argv[2])
