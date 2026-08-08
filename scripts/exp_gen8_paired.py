"""GEN8 PAREADO: razonamiento en canal separado (`think=True`) vs actual (`think=False`).

Diagnostico (E3 + D2, 2026-08-07):
  - Con think=False qwen3 razona DENTRO del cuerpo -> loop de deliberacion sin converger.
    Medido en "que es Superintendencia": 2000 tokens y seguia deliberando, 28 citas duplicadas.
  - Consecuencias: 13.1 citas/respuesta (4.2 unicas, precision 0.43) y RECHAZOS con el gold
    en RANK 0 (DIA x3, DIP x2, y otras 6 tras D2). El prompt YA pide respuesta corta
    ("1 oracion directa + 2-3 de detalle") y el modelo lo ignora porque no tiene otro lugar
    donde pensar.
  - Ademas el prompt exige "cada oracion termina con una cita" -> deliberar 20 oraciones
    emite 20 citas. Causa directa del efecto escopeta.

Este experimento cambia UNA sola variable: `ollama_think`.
Metricas: cita_ok pareado (McNemar) + calidad de cita (n_cits, precision) + tiempo.
Persiste el TEXTO de ambas respuestas (patron adoptado en E3).

⚠️ think=True es MAS LENTO. Es esperable; lo que se mide es si convierte.

Uso: BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_gen8_paired
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
from src.core import config as cfg

MODEL = "ollama/qwen3:30b-a3b"
SET = "data/eval/queries_balanced_v2_clean.jsonl"
OUTDIR = Path("data/eval/results/gen8_paired")


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
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)

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

    # retrieval IDENTICO en ambos brazos (solo cambia la generacion) -> 1 sola pasada
    print(f"=== FASE A: retrieval ({len(rows)}q, identico en ambos brazos) ===", flush=True)
    for q in rows:
        q["_docs"] = retr.retrieve(q["query"], top_k=10)

    cfg.settings.embed_4b_dense = False
    subprocess.run(["ollama", "stop", "qwen3-embedding:4b"], capture_output=True)
    try:
        import torch, gc; del r, retr.reranker; gc.collect(); torch.cuda.empty_cache()
    except Exception: pass

    def gen(qtext, docs, gs, think):
        cfg.settings.ollama_think = think
        for a in (1, 2, 3):
            try:
                t0 = time.time()
                res = generate_answer(qtext, docs, llm=llm, model=MODEL)
                txt = res["text"]
                cits = [(str(n), _normalize_art(str(x))) for n, x in extract_citations(txt)]
                uniq = list(dict.fromkeys(cits))
                good = [c for c in uniq if c in gs]
                return {
                    "ok": bool(good) and REFUSAL_TEXT.lower() not in txt.lower(),
                    "n_cits": len(cits), "n_uniq": len(uniq),
                    "prec": (len(good) / len(uniq)) if uniq else 0.0,
                    "secs": round(time.time() - t0, 1), "text": txt,
                }, False
            except Exception as ex:
                print(f"    ! fail '{qtext[:24]}' think={think} {type(ex).__name__}", flush=True)
                time.sleep(3)
        return {"ok": False, "n_cits": 0, "n_uniq": 0, "prec": 0.0, "secs": 0.0, "text": ""}, True

    print("=== FASE B: gen pareada (OFF think=False / ON think=True) ===", flush=True)
    nq = 0
    for i, q in enumerate(rows):
        if q["query"] in prev:
            q.update({k: v for k, v in prev[q["query"]].items() if k.startswith(("ok_", "off_", "on_", "err"))})
            continue
        gs = golds(q)
        off, e1 = gen(q["query"], q["_docs"], gs, False)
        on, e2 = gen(q["query"], q["_docs"], gs, True)
        q["ok_off"], q["ok_on"] = off["ok"], on["ok"]
        q["off_stats"], q["on_stats"] = off, on
        q["err"] = e1 or e2
        nq += 1
        if nq % 5 == 0:
            (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))
            print(f"  gen nuevas={nq}  [{i+1}/{len(rows)}]", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"detail": rows}, ensure_ascii=False, default=str))

    valid = [q for q in rows if not q.get("err") and q.get("off_stats")]
    off_t = sum(q["ok_off"] for q in valid); on_t = sum(q["ok_on"] for q in valid)
    won = sum(1 for q in valid if not q["ok_off"] and q["ok_on"])
    lost = sum(1 for q in valid if q["ok_off"] and not q["ok_on"])
    p = _mcnemar_p(lost, won)
    print(f"\n=== GEN8 think=False -> think=True (in_domain contestables) ===", flush=True)
    print(f"  cita_ok  OFF {off_t}/{len(valid)} -> ON {on_t}/{len(valid)}  (gano {won}, perdio {lost})", flush=True)
    print(f"  McNemar p={p:.4f}  ({'SIGNIFICATIVO' if p < 0.05 else 'ruido/flat'})", flush=True)
    if valid:
        for lbl, k in (("citas/resp", "n_cits"), ("citas unicas", "n_uniq"), ("precision", "prec"), ("segundos", "secs")):
            a = sum(q["off_stats"][k] for q in valid) / len(valid)
            b = sum(q["on_stats"][k] for q in valid) / len(valid)
            print(f"  {lbl:14} OFF {a:6.2f}  ->  ON {b:6.2f}", flush=True)
    for q in valid:
        if not q["ok_off"] and q["ok_on"]: print(f"  GANO: {q['query'][:60]}", flush=True)
    for q in valid:
        if q["ok_off"] and not q["ok_on"]: print(f"  PERDIO: {q['query'][:60]}", flush=True)


if __name__ == "__main__":
    main()
