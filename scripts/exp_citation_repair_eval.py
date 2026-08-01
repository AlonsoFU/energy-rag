"""Eval del experimento CITATION REPAIR (CiteFix-similarity, post-hoc).

Cuello que ataca: el gold llega al top-k del retrieval pero el LLM cita el
artículo vecino. La reparación puntúa RESPUESTA↔doc con el cross-encoder BGE y
AÑADE la cita del doc que mejor sostiene la respuesta si no estaba citada.

Diseño eficiente: la reparación es POST-HOC determinista sobre el texto ya
generado → genero UNA sola vez (baseline, flag off) y aplico repair sobre el
mismo texto a varios umbrales. La generación Ollama (el cuello de tiempo) corre
una vez; el barrido de umbral es gratis.

Métricas por set:
  - baseline cita_ok
  - repaired cita_ok por umbral  (MONÓTONO ≥ baseline: solo añade)
  - n_changed: respuestas donde se añadió una cita
  - precisión de añadidas: added_gold / added_total (cuántas añadidas eran gold
    vs ruido — el costo de 'post-racionalización', SIGIR 2025)
  - distribución de top_score (para calibrar umbral)

dev/holdout = no-regresión (monótono ⇒ cita_ok no baja; vigilamos precisión).

Uso: venv-gpu/bin/python -m scripts.exp_citation_repair_eval [top_k]
Requiere: USE_BGE_RERANKER=1, BGE_DEVICE=cuda, BGE_FP16=1, EMBEDDER_DEVICE=cpu.
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.citation_repair import repair_citations
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUTDIR = Path("data/eval/results/citation_repair")
SETS = [
    ("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
    ("dev",       "data/eval/queries_independent.jsonl"),
    ("holdout",   "data/eval/queries_holdout.jsonl"),
]
# Umbral en espacio de score del cross-encoder (bge-reranker-v2-m3 → logits).
# -99 = añadir siempre el mejor no-citado. Subir el umbral = añadir menos.
THRESHOLDS = [-99.0, 0.0, 2.0, 4.0, 6.0]


def _golds(q):
    out = [(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))]
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1)
        out.append((n, _normalize_art(a)))
    return set(out)


def _cited(citations, golds):
    return any((str(n), _normalize_art(str(a))) in golds for n, a in citations)


def main():
    top_k = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    assert cfg.settings.use_bge_reranker, "Requiere use_bge_reranker=True (repair usa BGE)"

    e = Qwen3Embedder()
    r = get_reranker()  # BGE — UNA instancia, compartida retriever + repair
    store = PostgresStore()
    llm = get_llm_provider()
    router = AdaptiveRouter(); router.train_default()
    pool = cfg.settings.retrieval_pool_depth
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    OUTDIR.mkdir(parents=True, exist_ok=True)
    print(f"=== CITATION REPAIR eval === top_k={top_k} thresholds={THRESHOLDS}", flush=True)

    for setname, path in SETS:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        agg = {"n": 0, "base_cita_ok": 0,
               "rep": {t: {"cita_ok": 0, "changed": 0, "added_total": 0, "added_gold": 0}
                       for t in THRESHOLDS}}
        detail = []
        for q in rows:
            if q.get("expected_norma") is None:
                continue  # negativas: la reparación no toca refusals (medidas aparte si hace falta)
            golds = _golds(q)
            branch, docs = adaptive.retrieve(q["query"], top_k=top_k)
            res = generate_answer(q["query"], docs, llm=llm)  # repair OFF (baseline)
            txt = res["text"]
            refused = REFUSAL_TEXT.lower() in txt.lower()
            agg["n"] += 1
            base_cits = extract_citations(txt)
            base_ok = _cited(base_cits, golds)
            agg["base_cita_ok"] += base_ok

            row = {"q": q["query"][:70], "cat": q.get("category"),
                   "gold": sorted(golds), "branch": branch,
                   "base_cits": [f"{n}/{a}" for n, a in base_cits], "base_ok": base_ok,
                   "refused": refused, "rep": {}}
            for t in THRESHOLDS:
                if refused:
                    rep_ok, added = base_ok, []
                    top_score = 0.0; changed = False
                else:
                    rep = repair_citations(txt, docs, r, max_add=cfg.settings.citation_repair_max_add,
                                           min_score=t)
                    rep_cits = extract_citations(rep["text"])
                    rep_ok = _cited(rep_cits, golds)
                    added = rep["added"]; top_score = rep["top_score"]; changed = rep["changed"]
                agg["rep"][t]["cita_ok"] += rep_ok
                agg["rep"][t]["changed"] += int(changed)
                for a in added:
                    agg["rep"][t]["added_total"] += 1
                    n_, ar_ = a.split("/", 1)
                    agg["rep"][t]["added_gold"] += int((n_, _normalize_art(ar_)) in golds)
                row["rep"][str(t)] = {"ok": rep_ok, "added": added,
                                      "top_score": round(top_score, 3), "changed": changed}
            detail.append(row)
            print(f"[{setname}] n={agg['n']} base_ok={agg['base_cita_ok']} "
                  f"rep@-99={agg['rep'][-99.0]['cita_ok']} q={q['query'][:45]}", flush=True)

        out = {"set": setname, "top_k": top_k, "n": agg["n"],
               "base_cita_ok": agg["base_cita_ok"], "rep": {str(k): v for k, v in agg["rep"].items()},
               "detail": detail}
        (OUTDIR / f"{setname}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"\n=== {setname}: n={agg['n']} baseline cita_ok={agg['base_cita_ok']}", flush=True)
        for t in THRESHOLDS:
            rr = agg["rep"][t]
            prec = f"{rr['added_gold']}/{rr['added_total']}" if rr["added_total"] else "—"
            print(f"    thr={t:>5}: cita_ok={rr['cita_ok']:2d}  (+{rr['cita_ok']-agg['base_cita_ok']})"
                  f"  changed={rr['changed']:2d}  add_prec={prec}", flush=True)
        print(f"-> {OUTDIR / f'{setname}.json'}\n", flush=True)


if __name__ == "__main__":
    main()
