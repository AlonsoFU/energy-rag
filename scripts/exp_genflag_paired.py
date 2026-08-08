"""Runner PAREADO genérico para experimentos que solo tocan la GENERACIÓN.

El retrieval es identico en ambos brazos (una sola pasada) y se cachea en disco, asi que
experimentos sucesivos sobre el mismo set no lo repiten. Solo cambia el flag bajo prueba.

  FLAG=prompt_prefer_definition NAME=gen8b PYTHONPATH=. BGE_DEVICE=cuda \
      venv/bin/python -m scripts.exp_genflag_paired

Env:
  FLAG     nombre del atributo en cfg.settings a togglear
  NAME     subcarpeta de resultados en data/eval/results/<NAME>/
  OFF_VAL  valor del brazo OFF (default False). Se castea al tipo del default del flag.
  ON_VAL   valor del brazo ON  (default True).  Permite barrer enteros (ej top_k 10 -> 5).
  LIMIT    (opcional) recorta el set, para pruebas rapidas

Mide cita_ok pareado (McNemar) + calidad de cita (n_cits, n_uniq, precision) + segundos,
y PERSISTE el texto de ambas respuestas (sin eso no se puede auditar despues — lección de E3).
Resumible: relee result.json y saltea pares ya hechos.
"""
import json, os, subprocess, time, math
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

MODEL = "ollama/qwen3:30b-a3b"
SET = "data/eval/queries_balanced_v2_clean.jsonl"
FLAG = os.environ["FLAG"]
NAME = os.environ.get("NAME", FLAG)
LIMIT = int(os.environ.get("LIMIT", "0"))


def _cast(raw, default_kind):
    """Castea OFF_VAL/ON_VAL al tipo del default del flag (bool o int)."""
    if raw is None:
        return None
    if isinstance(default_kind, bool):
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default_kind, int):
        return int(raw)
    return raw
OUTDIR = Path(f"data/eval/results/{NAME}")
DOCS_CACHE = Path("data/eval/results/_docs_cache_balanced_clean.json")


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def main():
    rows = [json.loads(l) for l in Path(SET).read_text().splitlines() if l.strip()]
    rows = [q for q in rows if q.get("category") == "in_domain" and not q.get("unanswerable")]
    if LIMIT: rows = rows[:LIMIT]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    assert hasattr(cfg.settings, FLAG), f"flag inexistente: {FLAG}"
    _default = getattr(cfg.settings, FLAG)
    off_val = _cast(os.environ.get("OFF_VAL"), _default)
    on_val = _cast(os.environ.get("ON_VAL"), _default)
    if off_val is None: off_val = False if isinstance(_default, bool) else _default
    if on_val is None: on_val = True if isinstance(_default, bool) else _default
    print(f"[FLAG] {FLAG}: OFF={off_val!r}  ON={on_val!r}", flush=True)
    llm = get_llm_provider()

    # ---- retrieval: cache en disco (identico en ambos brazos y entre experimentos de gen) ----
    cache = {}
    if DOCS_CACHE.exists():
        try: cache = json.load(open(DOCS_CACHE))
        except Exception: cache = {}
    faltan = [q for q in rows if q["query"] not in cache]
    if faltan:
        print(f"=== FASE A: retrieval de {len(faltan)}q (cache tiene {len(cache)}) ===", flush=True)
        subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
        e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore()
        cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
        pool = cfg.settings.retrieval_pool_depth
        retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
        for i, q in enumerate(faltan):
            cache[q["query"]] = retr.retrieve(q["query"], top_k=10)
            if (i + 1) % 50 == 0: print(f"  retrieval {i+1}/{len(faltan)}", flush=True)
        DOCS_CACHE.write_text(json.dumps(cache, ensure_ascii=False, default=str))
        cfg.settings.embed_4b_dense = False
        subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
        try:
            import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
        except Exception: pass
    else:
        print(f"=== FASE A: retrieval 100% cacheado ({len(cache)} queries) ===", flush=True)
    for q in rows:
        q["_docs"] = cache[q["query"]]

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("ok_on") is not None and c.get("ok_off") is not None:
                    prev[c["query"]] = c
            print(f"[RESUME] {len(prev)} pares ya generados", flush=True)
        except Exception as ex:
            print(f"[RESUME] fallo: {type(ex).__name__}", flush=True)

    def gen(qtext, docs, gs, val):
        setattr(cfg.settings, FLAG, val)
        for a in (1, 2, 3):
            try:
                t0 = time.time()
                txt = generate_answer(qtext, docs, llm=llm, model=MODEL)["text"]
                cits = [(str(n), _normalize_art(str(x))) for n, x in extract_citations(txt)]
                uniq = list(dict.fromkeys(cits))
                good = [c for c in uniq if c in gs]
                return {"ok": bool(good) and REFUSAL_TEXT.lower() not in txt.lower(),
                        "n_cits": len(cits), "n_uniq": len(uniq),
                        "prec": (len(good) / len(uniq)) if uniq else 0.0,
                        "secs": round(time.time() - t0, 1), "text": txt}, False
            except Exception as ex:
                print(f"    ! fail '{qtext[:24]}' {FLAG}={val} {type(ex).__name__}", flush=True)
                time.sleep(3)
        return {"ok": False, "n_cits": 0, "n_uniq": 0, "prec": 0.0, "secs": 0.0, "text": ""}, True

    print(f"=== FASE B: gen pareada  OFF({FLAG}={off_val!r}) / ON({FLAG}={on_val!r}) ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        if q["query"] in prev:
            for k in ("ok_off", "ok_on", "off_stats", "on_stats", "err"):
                if k in prev[q["query"]]: q[k] = prev[q["query"]][k]
            continue
        gs = golds(q)
        off, e1 = gen(q["query"], q["_docs"], gs, off_val)
        on, e2 = gen(q["query"], q["_docs"], gs, on_val)
        q["ok_off"], q["ok_on"] = off["ok"], on["ok"]
        q["off_stats"], q["on_stats"], q["err"] = off, on, e1 or e2
        nq += 1
        if nq % 5 == 0:
            (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            print(f"  gen nuevas={nq}  [{i+1}/{len(rows)}]", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
    setattr(cfg.settings, FLAG, _default)

    valid = [q for q in rows if not q.get("err") and q.get("off_stats")]
    off_t = sum(q["ok_off"] for q in valid); on_t = sum(q["ok_on"] for q in valid)
    won = sum(1 for q in valid if not q["ok_off"] and q["ok_on"])
    lost = sum(1 for q in valid if q["ok_off"] and not q["ok_on"])
    p = _mcnemar_p(lost, won)
    print(f"\n=== {NAME}: {FLAG} {off_val!r} -> {on_val!r} (in_domain contestables) ===", flush=True)
    print(f"  cita_ok  OFF {off_t}/{len(valid)} -> ON {on_t}/{len(valid)}  (gano {won}, perdio {lost})", flush=True)
    print(f"  McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/flat'})", flush=True)
    for lbl, k in (("citas/resp", "n_cits"), ("citas unicas", "n_uniq"), ("precision", "prec"), ("segundos", "secs")):
        a = sum(q["off_stats"][k] for q in valid) / max(1, len(valid))
        b = sum(q["on_stats"][k] for q in valid) / max(1, len(valid))
        print(f"  {lbl:14} OFF {a:6.2f}  ->  ON {b:6.2f}", flush=True)
    for q in valid:
        if not q["ok_off"] and q["ok_on"]: print(f"  GANO: {q['query'][:60]}", flush=True)
    for q in valid:
        if q["ok_off"] and not q["ok_on"]: print(f"  PERDIO: {q['query'][:60]}", flush=True)


if __name__ == "__main__":
    main()
