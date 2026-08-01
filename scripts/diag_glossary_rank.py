"""Retrieval-only: rango del gold post-RRF/post-BGE para queries de glosario.
Señal rápida del efecto del term-prefix (correr con índice nuevo).
Uso: ./venv-gpu/bin/python -m scripts.diag_glossary_rank
"""
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights

CASES = [
    ("qué es la tasa de actualización según la ley", "258171", "225", "dev MISS(182bis)"),
    ("qué se entiende por servicios complementarios en el sistema eléctrico", "258171", "225", "dev MISS(1047565)"),
    ("qué se necesita para que una central se considere de cogeneración eficiente", "258171", "225", "dev MISS"),
    ("máxima cantidad de energía que un sistema de almacenamiento puede entregar, definición", "258171", "225", "dev MISS(vacío)"),
    ("qué es la suficiencia de potencia de una unidad", "250604", "13", "dev MISS(250604/59)"),
    # no-regresión: defs que YA pasaban
    ("qué es un usuario o consumidor final", "258171", "225", "dev PASS (no-reg)"),
    ("qué es la energía renovable no convencional", "258171", "225", "dev PASS (no-reg)"),
]


def rank_of(pool, gn, ga):
    for i, c in enumerate(pool):
        if str(c.get("id_norma")) == gn and str(c.get("articulo_numero")) == ga:
            return i + 1
    return None


def main():
    store, emb, rr = PostgresStore(), Qwen3Embedder(), get_reranker()
    print(f"reranker={type(rr).__name__}")
    for q, gn, ga, tag in CASES:
        bm25 = store.search_bm25(q, top_k=50)
        vec = store.search_vector(emb.embed([q])[0], top_k=50)
        fused = rrf_fusion([bm25, vec], k=60, weights=_length_weights(q))[:50]
        r_rrf = rank_of(fused, gn, ga)
        scored = rr.rerank(q, [c["contextual_text"] for c in fused], top_k=30)
        bge = [{**fused[i], "score": float(s)} for i, s in scored]
        r_bge = rank_of(bge, gn, ga)
        print(f"  RRF={str(r_rrf):>4}  BGE={str(r_bge):>4}  gold {gn}/{ga}  [{tag}]  {q[:55]}")


if __name__ == "__main__":
    main()
