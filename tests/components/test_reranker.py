import pytest


@pytest.mark.slow
def test_reranker_orders_by_relevance():
    from src.components.reranker import Qwen3Reranker

    rr = Qwen3Reranker()
    query = "potencia firme"
    docs = [
        "Las empresas distribuidoras facturan según consumo medido.",  # irrelevant
        "Se entenderá por potencia firme la capacidad de generación...",  # relevant
        "El presupuesto fiscal se aprueba en noviembre.",  # irrelevant
    ]
    scored = rr.rerank(query, docs, top_k=3)
    # Most relevant doc should be first
    assert scored[0][0] == 1  # index of relevant doc
