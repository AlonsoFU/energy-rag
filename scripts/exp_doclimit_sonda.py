"""FASE 1.1b — SONDA DE LATENCIA de `answer_doc_limit`. No mide calidad.

Por que una sonda antes del pareado: el pareado de calidad sobre las 114 operativas cuesta
~5 h de GPU. Solo vale la pena si ALGUN valor de doc_limit acerca la mediana al objetivo
de <=45 s. Si el mejor valor se queda en 70 s, el pareado no cambia la decision y no se corre.

Que hace: misma query, mismo retrieval (se cachea UNA vez por query — doc_limit solo recorta
lo que ve el GENERADOR, el retrieval es identico), y se cronometra la generacion con cada
valor de doc_limit. Orden de valores rotado por query para que el calentamiento del modelo
no se le cargue siempre al mismo brazo.

  PYTHONPATH=. venv/bin/python -m scripts.exp_doclimit_sonda

Env: N (queries, default 12), VALORES (default "0,5,3,2").
"""
import json, os, statistics, time
from pathlib import Path

from src.components.embedder import Qwen3Embedder
from src.components.llm import get_llm_provider
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.core import config as cfg
from src.pipelines.generate import generate_answer
from src.pipelines.retrieve import SimpleRetriever

MODEL = "ollama/qwen3:30b-a3b"
SET = Path(os.environ.get("SET", "data/eval/queries_operativas_v1.jsonl"))
N = int(os.environ.get("N", "12"))
VALORES = [int(v) for v in os.environ.get("VALORES", "0,5,3,2").split(",")]
OUT = Path("data/eval/results/doclimit_sonda/result.json")


def main():
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    rows = [q for q in rows if not q.get("unanswerable")]
    # muestreo determinista y REPARTIDO por el set (no los primeros N, que son todos
    # complex_v3 y sesgarian la mediana hacia un solo tipo de pregunta).
    paso = max(1, len(rows) // N)
    rows = rows[::paso][:N]
    OUT.parent.mkdir(parents=True, exist_ok=True)

    llm = get_llm_provider()
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore()
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
    cfg.settings.embed_4b_cpu = True          # ver exp_selfcons_n1: si no, desaloja el LLM
    cfg.settings.alias_union = True; cfg.settings.glossary_inject = True
    cfg.settings.glossary_lookup = True; cfg.settings.intent_gate = True
    cfg.settings.ambiguity_disclose = True; cfg.settings.filtrar_fuera_dominio = True
    cfg.settings.self_consistency_n = 3       # config VIGENTE; no se togglea aca
    retr = SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)

    prev = json.load(open(OUT)) if OUT.exists() else {}
    print(f"=== sonda doclimit: {len(rows)} queries x {VALORES}  (n=3 vigente) ===", flush=True)

    for i, q in enumerate(rows):
        qt = q["query"]
        docs = retr.retrieve(qt, top_k=10)    # UNA vez: identico para todos los brazos
        orden = VALORES[i % len(VALORES):] + VALORES[:i % len(VALORES)]   # rota el calentamiento
        for v in orden:
            k = f"{v}|{qt}"
            if k in prev:
                continue
            cfg.settings.answer_doc_limit = v
            try:
                t0 = time.time()
                txt = generate_answer(qt, docs, llm=llm, model=MODEL)["text"]
                prev[k] = {"secs": round(time.time() - t0, 1), "chars": len(txt), "v": v}
            except Exception as ex:
                print(f"  ! {type(ex).__name__} v={v} '{qt[:30]}'", flush=True)
                prev[k] = {"secs": None, "chars": 0, "v": v}
            OUT.write_text(json.dumps(prev, ensure_ascii=False))
        print(f"  [{i+1}/{len(rows)}] {qt[:50]}", flush=True)

    cfg.settings.answer_doc_limit = 0
    print(f"\n=== mediana de segundos por doc_limit (n=3, {len(rows)} queries) ===", flush=True)
    for v in VALORES:
        s = [x["secs"] for x in prev.values() if x["v"] == v and x["secs"]]
        if not s:
            continue
        print(f"  doc_limit={v:<2}  mediana {statistics.median(s):6.1f} s   "
              f"media {statistics.mean(s):6.1f} s   n={len(s)}", flush=True)


if __name__ == "__main__":
    main()
