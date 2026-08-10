"""D2 PAREADO: extractor 'leyenda de variable' (+103 fragmentos) sobre la config vigente.

El cambio es de DATOS (tabla `fragmentos_definicion`: 608 -> 713), no de flag, así que el brazo OFF
necesita la tabla VIEJA. Se hace SWAP de tablas entre las dos pasadas de retrieval:
    fragmentos_definicion <-> fragmentos_definicion_bak2
Ambos brazos generan en LA MISMA sesión (pares limpios, sin flicker de LLM entre corridas).

Robusto: el swap va en try/finally y al final SIEMPRE deja la tabla NUEVA como
`fragmentos_definicion`. Si el proceso muere entre swaps, revisar con:
    SELECT count(*) FROM fragmentos_definicion;   -- 713 = nueva (correcta), 608 = vieja

Resumible: relee result.json y saltea pares ya generados (clave = query).

Uso: BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_d2_paired
"""
import json, subprocess, time, math
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.storage.connection import with_connection
from src.core import config as cfg

MODEL = "ollama/qwen3:30b-a3b"
SET = "data/eval/queries_balanced_v2_clean.jsonl"
OUTDIR = Path("data/eval/results/d3_trigger")


def swap_tables():
    """Intercambia fragmentos_definicion <-> fragmentos_definicion_bak2."""
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE fragmentos_definicion RENAME TO _fd_swap_tmp")
        cur.execute("ALTER TABLE fragmentos_definicion_bak2 RENAME TO fragmentos_definicion")
        cur.execute("ALTER TABLE _fd_swap_tmp RENAME TO fragmentos_definicion_bak2")
        conn.commit()


def n_frags():
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM fragmentos_definicion")
        return cur.fetchone()[0]


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _ok(res, gs):
    cits = extract_citations(res["text"])
    return any((str(n), _normalize_art(str(a))) in gs for n, a in cits) and REFUSAL_TEXT.lower() not in res["text"].lower()


def _ids(docs): return {d["id"] for d in docs}


def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def main():
    rows = [json.loads(l) for l in Path(SET).read_text().splitlines() if l.strip()]
    # solo in_domain CONTESTABLES (E0c: las unanswerable puntuan rechazo=acierto, no cita_ok)
    rows = [q for q in rows if q.get("category") == "in_domain" and not q.get("unanswerable")]
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
    assert cfg.settings.glossary_inject, "glossary_inject debe estar ON (config vigente)"
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("ok_on") is not None and c.get("ok_off") is not None:
                    prev[c["query"]] = (c["ok_off"], c["ok_on"])
            print(f"[RESUME] {len(prev)} pares ya generados", flush=True)
        except Exception as ex:
            print(f"[RESUME] fallo: {type(ex).__name__}", flush=True)

    print(f"=== FASE A1: retrieval con tabla NUEVA ({n_frags()} frags) ===", flush=True)
    for q in rows:
        q["_on"] = retr.retrieve(q["query"], top_k=10)

    swapped = False
    try:
        swap_tables(); swapped = True
        print(f"=== FASE A2: retrieval con tabla VIEJA ({n_frags()} frags) ===", flush=True)
        for q in rows:
            q["_off"] = retr.retrieve(q["query"], top_k=10)
    finally:
        if swapped:
            swap_tables()
            print(f"[swap restaurado] fragmentos_definicion = {n_frags()} filas (713 = nueva OK)", flush=True)

    changed = sum(1 for q in rows if _ids(q["_off"]) != _ids(q["_on"]))
    for q in rows:
        q["_chg"] = _ids(q["_off"]) != _ids(q["_on"])
    print(f"  top-10 cambio en {changed}/{len(rows)}", flush=True)

    cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception: pass

    def gen(qtext, docs, gs):
        for a in (1, 2, 3):
            try: return _ok(generate_answer(qtext, docs, llm=llm, model=MODEL), gs), False
            except Exception as ex:
                print(f"    ! fail '{qtext[:24]}' {type(ex).__name__}", flush=True); time.sleep(3)
        return False, True

    print("=== FASE B: gen pareada ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        gs = golds(q)
        if q["query"] in prev:
            q["ok_off"], q["ok_on"] = prev[q["query"]]
            continue
        if q["_chg"]:
            q["ok_off"], e1 = gen(q["query"], q["_off"], gs)
            q["ok_on"], e2 = gen(q["query"], q["_on"], gs)
            q["err"] = e1 or e2
        else:
            ok, er = gen(q["query"], q["_off"], gs)
            q["ok_off"] = q["ok_on"] = ok; q["err"] = er
        nq += 1
        if nq % 5 == 0:
            (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            print(f"  gen nuevas={nq}  [{i+1}/{len(rows)}]", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))

    valid = [q for q in rows if not q.get("err")]
    off_t = sum(q["ok_off"] for q in valid); on_t = sum(q["ok_on"] for q in valid)
    won = sum(1 for q in valid if not q["ok_off"] and q["ok_on"])
    lost = sum(1 for q in valid if q["ok_off"] and not q["ok_on"])
    p = _mcnemar_p(lost, won)
    print(f"\n=== D2 leyenda-de-variable (608 -> 713 frags), in_domain contestables ===", flush=True)
    print(f"  OFF {off_t}/{len(valid)} -> ON {on_t}/{len(valid)}  (gano {won}, perdio {lost})", flush=True)
    print(f"  McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/flat'})", flush=True)
    for q in valid:
        if not q["ok_off"] and q["ok_on"]: print(f"  GANO: {q['query'][:60]}", flush=True)
    for q in valid:
        if q["ok_off"] and not q["ok_on"]: print(f"  PERDIO: {q['query'][:60]}", flush=True)


if __name__ == "__main__":
    main()
