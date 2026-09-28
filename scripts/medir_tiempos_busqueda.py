"""Tiempo de busqueda por etapa sobre 20 queries de dev (config adoptada, como en produccion).

Envuelve con cronometro las funciones reales (no las reimplementa): embed de la query (Ollama 4B),
BM25, busqueda vectorial, rerank BGE, y el total de SimpleRetriever.retrieve. El resto del total
= fusion RRF, glosario, alias, llamadas al LLM de los filtros, expansion jerarquica.
Uso: env PYTHONPATH=. HF_HUB_OFFLINE=1 HF_HOME=/home/alonso/datos/hf venv/bin/python -m scripts.medir_tiempos_busqueda
"""
import collections, json, statistics as st, time
from src.core import config as cfg
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines import retrieve as R

T = collections.defaultdict(float)


def reloj(nombre, f):
    def g(*a, **k):
        t0 = time.perf_counter()
        try:
            return f(*a, **k)
        finally:
            T[nombre] += time.perf_counter() - t0
    return g


R._embed_4b_query = reloj("embed_query", R._embed_4b_query)
for m in ("search_bm25",):
    setattr(PostgresStore, m, reloj("bm25", getattr(PostgresStore, m)))
for m in ("search_vector_4b_1024", "search_vector_def_4b_1024", "search_vector_4b", "search_vector"):
    if hasattr(PostgresStore, m):
        setattr(PostgresStore, m, reloj("vector_sql", getattr(PostgresStore, m)))

# misma config que el harness de eval (config adoptada)
cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
cfg.settings.alias_union = True; cfg.settings.glossary_inject = True
cfg.settings.glossary_lookup = True; cfg.settings.intent_gate = True
cfg.settings.ambiguity_disclose = True; cfg.settings.filtrar_fuera_dominio = True

llm = get_llm_provider(); e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore()
r.rerank = reloj("rerank", r.rerank)
retr = R.SimpleRetriever(store, e, r, top_bm25=cfg.settings.retrieval_pool_depth,
                         top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
qs = [json.loads(l)["query"] for l in open("data/eval/queries_operativas_v1.jsonl") if l.strip()][:21]
retr.retrieve(qs[0], top_k=10)            # calentamiento: carga de modelos, no se cuenta
T.clear()
tot = []
for q in qs[1:]:
    t0 = time.perf_counter(); retr.retrieve(q, top_k=10); tot.append(time.perf_counter() - t0)
n = len(tot)
print(f"n={n} queries (sin la de calentamiento)")
print(f"  TOTAL retrieve     media {st.mean(tot):6.2f} s   mediana {st.median(tot):6.2f} s   max {max(tot):6.2f} s")
for k in ("embed_query", "bm25", "vector_sql", "rerank"):
    print(f"  {k:18s} media {T[k]/n:6.2f} s")
print(f"  resto (LLM filtros, glosario, fusion)  media {st.mean(tot) - sum(T[k] for k in ('embed_query','bm25','vector_sql','rerank'))/n:6.2f} s")
