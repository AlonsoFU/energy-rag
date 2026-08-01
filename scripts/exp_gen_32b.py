"""Fase 1 (3090) — LLM de generación MÁS GRANDE para el muro de GENERACIÓN.

La 3090 (24GB) permite correr qwen3:32b (~20GB Q4), antes imposible en la GTX 1080 (8GB).
Hipótesis: el muro residual coloquial (118) y los gen-miss (104, 250604/2, 250604/8) NO son
de retrieval (el gold YA está en el contexto) sino de GENERACIÓN — el 9b no cita el gold que
tiene delante. Un LLM más capaz debería citarlo.

DISEÑO (aísla generación): se recupera UNA vez con la MEJOR config de retrieval
(4B-1024 + alias_union, BGE en GPU) y se CACHEA el pool de docs por query. Luego se genera
desde los MISMOS docs con 9b y con 32b → cualquier diferencia es PURA generación.

Two-phase para no exceder 24GB (32b=20GB y 9b=6.6GB no caben juntos):
  Fase A: retrieval (4B embed Ollama + BGE GPU), cachea docs.
  Fase B1: genera todas con 9b   (ollama stop 32b antes).
  Fase B2: genera todas con 32b  (ollama stop 9b antes).

Uso: PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_gen_32b [top_k]
Requiere: qwen3:32b pulled, embedding_4b_1024 poblada, alias_map.py.
"""
import json, sys, subprocess
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/gen_32b")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl"),
        ("holdout", "data/eval/queries_holdout.jsonl")]
M9, M32 = "ollama/qwen3.5:9b", "ollama/qwen3:32b"


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _cited(cits, golds):
    return any((str(n), _normalize_art(str(a))) in golds for n, a in cits)


def _ok(res, golds):
    return _cited(extract_citations(res["text"]), golds) and REFUSAL_TEXT.lower() not in res["text"].lower()


def _stop(model):
    subprocess.run(["ollama", "stop", model.replace("ollama/", "")], capture_output=True)


def main():
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    # libera VRAM de modelos residentes (keep_alive) antes de cargar BGE en GPU → evita OOM
    for m in ("qwen3:32b", "qwen3.5:9b", "qwen3-embedding:8b"):
        _stop("ollama/" + m)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    # mejor config de retrieval
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True

    # ---- FASE A: retrieval (cachea docs por query) ----
    print("=== FASE A: retrieval 4B-1024+alias (BGE GPU), cachea docs ===", flush=True)
    cache = []
    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma") is not None]
        for q in rows:
            docs = retr.retrieve(q["query"], top_k=top_k)
            cache.append({"set": setname, "q": q["query"], "golds": list(_golds(q)), "docs": docs})
        print(f"  [{setname}] {len([c for c in cache if c['set']==setname])} docs cacheados", flush=True)
    cfg.settings.embed_4b_dense = False; _stop("qwen3-embedding:4b")

    # ---- FASE B: generación 9b y 32b desde los MISMOS docs ----
    for label, model in [("9b", M9), ("32b", M32)]:
        other = M32 if model == M9 else M9
        _stop(other)
        print(f"=== FASE B-{label}: genera {len(cache)} con {model} ===", flush=True)
        for c in cache:
            golds = {tuple(g) for g in c["golds"]}
            res = generate_answer(c["q"], c["docs"], llm=llm, model=model)
            c[f"ok_{label}"] = _ok(res, golds)
            c[f"txt_{label}"] = res["text"][:200]

    # ---- agregado + diffs ----
    agg = {}
    for c in cache:
        a = agg.setdefault(c["set"], {"n": 0, "9b": 0, "32b": 0})
        a["n"] += 1; a["9b"] += c.get("ok_9b", False); a["32b"] += c.get("ok_32b", False)
    detail = [{"set": c["set"], "q": c["q"][:60], "gold": sorted(f"{n}/{ar}" for n, ar in {tuple(g) for g in c["golds"]}),
               "ok_9b": c.get("ok_9b"), "ok_32b": c.get("ok_32b")} for c in cache]
    (OUTDIR / "result.json").write_text(json.dumps({"top_k": top_k, "agg": agg, "detail": detail}, ensure_ascii=False, indent=2))
    print("\n=== VEREDICTO cita_ok (mismos docs: 9b vs 32b) ===", flush=True)
    for s, a in agg.items():
        print(f"  {s:10s} n={a['n']:2d}  9b={a['9b']:2d}  32b={a['32b']:2d}  ({a['32b']-a['9b']:+d})", flush=True)
    print("\n=== casos donde 32b GANA o PIERDE vs 9b ===", flush=True)
    for c in cache:
        if c.get("ok_9b") != c.get("ok_32b"):
            print(f"  {'GANA' if c.get('ok_32b') else 'PIERDE':6s} [{c['set']}] {c['q'][:55]}", flush=True)


if __name__ == "__main__":
    main()
