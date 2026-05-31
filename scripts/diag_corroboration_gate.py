"""Test (solo-lectura) del GATE DE CORROBORACIÓN para el Paso 2.

Diseño: el resolver LLM propone un (norma,art) sujeto; el gate solo lo
inyecta/promueve si el POOL de retrieval ya lo trajo (corroboración). Esto
evita el daño de forzar al tope un artículo equivocado no respaldado.

Este script NO re-corre el LLM (usa las elecciones deterministas ya medidas en
diag_llm_subject_resolver). Solo corre retrieval (embedder+reranker) para
medir, por query:
  - gold ∈ pool?            (techo de retrieval)
  - resolver_pick ∈ pool?   (¿el gate lo deja pasar?)
  - decisión del gate y si ayuda / daña / es neutral.
"""
import json
from pathlib import Path

from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.components.vectorstore import PostgresStore
from src.components.embedder import Qwen3Embedder
from src.components.reranker import Qwen3Reranker
from src.components.llm import get_llm_provider
from src.core import config as cfg
from src.pipelines.grounding import _normalize_art

EVAL = Path("data/eval/queries_independent.jsonl")
TOP_K = 20  # generoso, para medir corroboración (no el top-5 de prod)

# Elecciones del resolver (qwen3.5:9b, temp=0) ya medidas. (norma, art) o None.
RESOLVER_PICK = {
    "si una distribuidora incumple la normativa, ¿qué organismo la fiscaliza y sanciona?": ("29819", "2°"),
    "una empresa quiere conectar su línea a un sistema de transmisión de otro dueño, ¿qué principio se lo permite?": ("258171", "79"),
    "cada cuánto y quién hace el plan de obras de transmisión a largo plazo": ("258171", "87"),
    "el ente que resuelve discrepancias entre el coordinador y las empresas, ¿cómo se financia?": ("258171", "212-1"),
    "qué pasa con el voltaje cuando una subestación lo baja del nivel de transporte al de distribución": ("258171", "73"),
    "cómo se reparte la plata que pagan los usuarios dentro de un sistema de transmisión": ("1146553", "5"),
    "el coordinador tiene que vigilar que haya competencia en el sector, ¿en qué artículo?": ("258171", "212-1"),
    "máxima cantidad de energía que un sistema de almacenamiento puede entregar, definición": ("250604", "13"),
    "qué se necesita para que una central se considere de cogeneración eficiente": ("258171", "225"),
    "un cliente que puede negociar libremente su precio de electricidad, ¿qué categoría es?": ("1183783", "2"),
    "una línea nueva que aumenta la capacidad de una subestación existente, ¿qué tipo de obra es?": ("1160108", "2"),
    "quién aprueba finalmente el plan de expansión de la transmisión": ("1160108", "2"),
    "el documento que fija los precios de nudo de corto plazo, ¿en qué se basa?": None,
    "qué obligación tiene el coordinador respecto a la cadena de pagos": ("258171", "72-2"),
    "cómo se clasifican las instalaciones de transmisión en segmentos": ("258171", "73"),
}


def _in_pool(docs, norma, art):
    ta = _normalize_art(str(art))
    return any(str(d.get("id_norma")) == str(norma)
              and _normalize_art(str(d.get("articulo_numero"))) == ta for d in docs)


def main():
    pool = cfg.settings.retrieval_pool_depth
    e, r = Qwen3Embedder(), Qwen3Reranker()
    store = PostgresStore()
    llm = get_llm_provider()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    rows = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["category"] == "indep_complex"]

    gold_in = win = harm = neutral = 0
    for q in rows:
        query = q["query"]
        gold = (str(q["expected_norma"]), str(q["expected_articulo"]))
        _branch, docs = adaptive.retrieve(query, top_k=TOP_K)
        g_in = _in_pool(docs, *gold)
        gold_in += g_in
        pick = RESOLVER_PICK.get(query)
        pick_in = bool(pick) and _in_pool(docs, *pick)
        pick_ok = pick == gold
        # gate: solo promueve si pick ∈ pool
        if pick and pick_in:
            if pick_ok:
                verdict = "WIN  (promueve correcto corroborado)"; win += 1
            else:
                verdict = "HARM (promueve equivocado corroborado)"; harm += 1
        else:
            verdict = "neutral (gate descarta / sin pick)"; neutral += 1
        print(f"gold={gold[0]}/{gold[1]} ∈pool={'Y' if g_in else 'N'} | "
              f"pick={pick} ∈pool={'Y' if pick_in else 'N'} ok={pick_ok} | {verdict}")
        print(f"   {query[:75]}")

    n = len(rows)
    print(f"\n== RESUMEN gate (top_k={TOP_K}) ==")
    print(f"gold ∈ pool (techo retrieval) : {gold_in}/{n}")
    print(f"gate WIN  (promueve correcto) : {win}/{n}")
    print(f"gate HARM (promueve erróneo)  : {harm}/{n}")
    print(f"gate neutral                  : {neutral}/{n}")


if __name__ == "__main__":
    main()
