"""Qué TIPOS de pregunta sabe responder el sistema, y cuáles no.

Motivo: hacerle una pregunta real al sistema destapó un modo de falla que ningún set de
evaluación detecta (exp #62) — ante una pregunta que exige comparar artículos con plazos
distintos, el modelo delibera en inglés y agota el presupuesto sin cerrar. Los sets propios
apuntan a definiciones puntuales, que se responden con UNA fuente.

La taxonomía no la invento: sale del estándar de RAG y de LegalBench.
  CRAG / MultiHop-RAG   inference · comparison · temporal · null
                        multi-hop se subdivide en bridge · intersection · comparison · temporal
  LegalBench            issue-spotting · rule-recall · rule-application · rule-conclusion ·
                        interpretation · rhetorical-understanding
  Legal RAG             el `temporal misgrounding` (citar norma no vigente) es modo propio

Acá NO se mide acierto contra un gold: se mide si el sistema **cierra una respuesta usable**.
Esa es la falla que apareció, y es previa a cualquier medición de precisión — una respuesta que
no existe no se puede evaluar.

  PYTHONPATH=. venv/bin/python -m scripts.exp_tipos_pregunta [--limit N]
"""
import argparse
import json
import os
import re
import time
from pathlib import Path

from src.components.embedder import Qwen3Embedder
from src.components.llm import get_llm_provider
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.core import config as cfg
from src.pipelines.generate import generate_answer
from src.pipelines.retrieve import SimpleRetriever

MODEL = "ollama/qwen3:30b-a3b"
SET = Path("data/eval/queries_tipos_v1.jsonl")
# NAME nombra la corrida. Existe porque el 04-09 se encolo una re-medicion con la config
# adoptada y el script RESUMIO el archivo del 01-09: 12/12 ya estaban cacheados, termino en
# 7 segundos, imprimio el resultado viejo y el runner lo marco OK. Un log verde sin haber
# medido nada. Con NAME cada corrida escribe su propio archivo.
NAME = os.environ.get("NAME", "tipos_pregunta")
OUT = Path(f"data/eval/results/{NAME}.json")
THINK = os.environ.get("THINK", "") == "1"      # exp #63: forzar think a mano (pre-adopcion)

# Marcadores de que la respuesta NO cerró: quedó el monólogo de deliberación en vez del texto.
# No es una lista de palabras prohibidas: son las muletillas con que el modelo razona EN INGLES
# cuando no termina, y la pregunta se hizo en castellano.
NO_CERRO = re.compile(r"\b(let's tackle|I need to check|Looking at|Wait, the user|"
                      r"First, I'll|Next, \[Art|So that's|But the question is)\b", re.I)
CITA = re.compile(r"\[[^\]]*art[^\]]*\]", re.I)


def diagnostico(txt):
    """Cierra / no cierra / rechaza — y por qué."""
    t = (txt or "").strip()
    if not t:
        return "VACIA", "el modelo no devolvio nada"
    if NO_CERRO.search(t):
        return "NO CIERRA", "devolvio el razonamiento crudo, sin respuesta final"
    # rechazo explicito: el sistema dice que no lo encuentra en el corpus
    if re.search(r"no (?:se )?(?:encuentr|dispon|hay)|fuera del (?:corpus|[áa]mbito)|"
                 r"no (?:puedo|cuento con)", t[:400], re.I) and not CITA.search(t):
        return "RECHAZA", "dice que no esta en el corpus"
    n = len(CITA.findall(t))
    if n == 0:
        return "SIN CITA", "respondio pero sin citar articulo"
    return "OK", f"{n} citas"


def main(limit=0):
    rows = [json.loads(l) for l in SET.read_text().splitlines() if l.strip()]
    if limit:
        rows = rows[:limit]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = Path(str(OUT).replace(".json", "_think.json")) if THINK else OUT
    prev = json.loads(out.read_text()) if out.exists() else {}

    llm = get_llm_provider()
    store = PostgresStore()
    cfg.settings.embed_4b_dense = True
    cfg.settings.embed_4b_dim = 1024
    cfg.settings.embed_4b_cpu = True          # que no pelee VRAM con el LLM
    if THINK:
        # exp #63: con think=False el modelo razona DENTRO de la respuesta y no cierra.
        # num_predict_think=6000 ya esta calibrado en config: con 2000 se queda sin tokens
        # ANTES de responder y devuelve vacio en ~55% de los casos.
        cfg.settings.ollama_think = True
    retr = SimpleRetriever(store, Qwen3Embedder(), get_reranker(),
                           top_bm25=cfg.settings.retrieval_pool_depth,
                           top_vector=cfg.settings.retrieval_pool_depth, llm=llm)

    # Se imprime la config EFECTIVA, no la variable de entorno. Desde el 04-09 lo que manda
    # es `answer_think` (adoptado, solo en la ruta de respuesta): el banner viejo decia
    # "think=OFF" mientras la respuesta SI razonaba en canal separado.
    print(f"=== {len(rows)} preguntas · {len(set(r['tipo'] for r in rows))} tipos · "
          f"THINK_env={'ON' if THINK else 'OFF'} · "
          f"answer_think={getattr(cfg.settings, 'answer_think', False)} · "
          f"ollama_think={cfg.settings.ollama_think} · "
          f"pendientes={sum(1 for r in rows if r['query'] not in prev)}/{len(rows)} ===\n",
          flush=True)
    for i, q in enumerate(rows, 1):
        if q["query"] in prev:
            continue
        t0 = time.time()
        try:
            docs = retr.retrieve(q["query"], top_k=10)
            txt = generate_answer(q["query"], docs, llm=llm, model=MODEL)["text"]
        except Exception as ex:
            txt = ""
            print(f"  ! {type(ex).__name__}", flush=True)
        estado, motivo = diagnostico(txt)
        seg = round(time.time() - t0, 1)
        prev[q["query"]] = {"tipo": q["tipo"], "estado": estado, "motivo": motivo,
                            "secs": seg, "docs": len(docs), "text": (txt or "")[:1500]}
        out.write_text(json.dumps(prev, ensure_ascii=False, indent=1))
        print(f"[{i}/{len(rows)}] {q['tipo']:<18} {estado:<10} {seg:>5.0f}s  {motivo}", flush=True)
        print(f"          {q['query'][:74]}", flush=True)

    import collections
    print("\n=== por TIPO ===", flush=True)
    por = collections.defaultdict(list)
    for v in prev.values():
        por[v["tipo"]].append(v["estado"])
    for t, es in sorted(por.items()):
        ok = sum(1 for e in es if e in ("OK", "RECHAZA"))
        print(f"  {t:<20} {ok}/{len(es)} usable   {es}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    main(ap.parse_args().limit)
