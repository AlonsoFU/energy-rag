"""NO-REGRESIÓN de la config vigente sobre los sets que NO se usaron en la campaña.

Hueco detectado 2026-08-08: el protocolo del proyecto exige "medir dev Y held-out (caza
overfit)", pero TODA la campaña 2026-08 se midió solo sobre `balanced_v2_clean` (267q).
Se adoptaron 6 cambios sin verificarlos fuera de ese set:
  glossary_inject · D2 leyenda-de-variable · ollama_num_ctx · ollama_num_predict
  parser de ordinales (CITATION_PATTERN) · strip del bloque <think>

Riesgo concreto: `glossary_inject` y D2 se DISEÑARON mirando fallas de balanced_v2 → son los
candidatos naturales a overfit. Los otros 4 son correcciones de bug, menos sospechosas.

Este script NO es un A/B: mide la config vigente sobre cada set y compara contra el
histórico documentado (`CLAUDE.md`), que se midió antes de la campaña:
    coloquial_v2  37/39   ·  independent(dev)  36/44*  ·  holdout  17/18*
    (*los archivos hoy tienen 49 y 24 filas; se reporta el n real y el % para comparar)

Uso: BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_noregresion
Resumible por set.
"""
import json, subprocess, time
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
OUTDIR = Path("data/eval/results/noregresion")
SETS = [
    ("coloquial", "data/eval/queries_coloquial_v2.jsonl", "37/39 (95%)"),
    ("dev_independent", "data/eval/queries_independent.jsonl", "36/44 (82%)"),
    ("holdout", "data/eval/queries_holdout.jsonl", "17/18 (94%)"),
]


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def main():
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    print(f"config: glossary_inject={cfg.settings.glossary_inject} num_ctx={cfg.settings.ollama_num_ctx} "
          f"num_predict={cfg.settings.ollama_num_predict}", flush=True)

    resumen = []
    for name, path, historico in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rp = OUTDIR / f"{name}.json"
        prev = {}
        if rp.exists():
            try: prev = {c["query"]: c for c in json.load(open(rp))["detail"] if c.get("ok") is not None}
            except Exception: pass
        print(f"\n=== {name}: {len(rows)}q (historico {historico}) [resume {len(prev)}] ===", flush=True)
        out = []
        for i, q in enumerate(rows):
            if q["query"] in prev:
                out.append(prev[q["query"]]); continue
            gs = golds(q)
            docs = retr.retrieve(q["query"], top_k=10)
            txt, err = "", False
            for a in (1, 2, 3):
                try:
                    txt = generate_answer(q["query"], docs, llm=llm, model=MODEL)["text"]; break
                except Exception as ex:
                    print(f"    ! fail '{q['query'][:22]}' {type(ex).__name__}", flush=True)
                    time.sleep(3); err = (a == 3)
            cits = [(str(n), _normalize_art(str(x))) for n, x in extract_citations(txt)]
            uniq = list(dict.fromkeys(cits))
            good = [c for c in uniq if c in gs]
            rec = {"query": q["query"], "gold": sorted(f"{n}/{a}" for n, a in gs), "err": err,
                   "ok": bool(good) and REFUSAL_TEXT.lower() not in txt.lower(),
                   "n_uniq": len(uniq), "prec": (len(good) / len(uniq)) if uniq else 0.0,
                   "text": txt}
            out.append(rec)
            if (i + 1) % 5 == 0:
                rp.write_text(json.dumps({"detail": out}, ensure_ascii=False, default=str))
                print(f"  {i+1}/{len(rows)}", flush=True)
        rp.write_text(json.dumps({"detail": out}, ensure_ascii=False, default=str))
        val = [x for x in out if not x["err"]]
        ok = sum(x["ok"] for x in val)
        prec = sum(x["prec"] for x in val) / max(1, len(val))
        uq = sum(x["n_uniq"] for x in val) / max(1, len(val))
        print(f"  --> {name}: {ok}/{len(val)} = {100*ok/max(1,len(val)):.1f}%  (historico {historico})  "
              f"citas_uniq {uq:.2f}  precision {prec:.2f}", flush=True)
        resumen.append((name, ok, len(val), historico, prec))
        for x in val:
            if not x["ok"]: print(f"      FALLA gold={x['gold'][:2]} | {x['query'][:52]}", flush=True)

    print("\n=== RESUMEN NO-REGRESIÓN (config vigente vs histórico pre-campaña) ===", flush=True)
    for name, ok, n, hist, prec in resumen:
        print(f"  {name:16} {ok}/{n} = {100*ok/max(1,n):5.1f}%   historico {hist:14}  precision {prec:.2f}", flush=True)


if __name__ == "__main__":
    main()
