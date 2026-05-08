import pytest


# ----------------------- Unit tests -----------------------

def test_rrf_combines_two_rankings():
    from src.pipelines.retrieve import rrf_fusion
    list_a = [{"id": 1}, {"id": 2}, {"id": 3}]
    list_b = [{"id": 3}, {"id": 1}, {"id": 4}]
    fused = rrf_fusion([list_a, list_b], k=60)
    ids = [x["id"] for x in fused]
    assert 1 in ids and 3 in ids
    assert ids.index(1) < ids.index(2)
    assert ids.index(3) < ids.index(4)


def test_extract_query_concepts():
    from src.pipelines.retrieve import extract_query_concepts
    conceptos = [
        {"nombre": "Comisión", "aliases": ["CNE"]},
        {"nombre": "potencia firme", "aliases": []},
    ]
    # Canonical-name match
    found = extract_query_concepts("¿qué hace la Comisión?", conceptos)
    coma = next(c for c in found if c["name"] == "Comisión")
    assert coma["matched_by_alias"] is False

    # Alias match
    found_alias = extract_query_concepts("qué es la CNE", conceptos)
    coma_alias = next(c for c in found_alias if c["name"] == "Comisión")
    assert coma_alias["matched_by_alias"] is True


# ----------------------- Integration tests -----------------------

@pytest.mark.integration
def test_graph_boost_promotes_definitoria(db_clean):
    from src.components.vectorstore import PostgresStore
    from src.core.models import Norma, Articulo, Fragmento, Concepto, Referencia
    from src.pipelines.retrieve import graph_boost
    s = PostgresStore()
    s.upsert_norma(Norma(id_norma="DECRETO_10", tipo="DECRETO", numero="10",
                         titulo="X", clase="reglamento_base"))
    a_id = s.upsert_articulo(Articulo(id_norma="DECRETO_10", numero="2°", texto="x"))
    s.upsert_fragmento(Fragmento(articulo_id=a_id, chunk_index=0,
        text="r", contextual_text="c", embedding=[0.0]*1024))
    c_id = s.upsert_concepto(Concepto(nombre="COMA", definicion="d"))
    s.upsert_referencia(Referencia(
        origen_articulo_id=a_id, destino_concepto_id=c_id,
        tipo_relacion="define_termino", confianza=1.0, metodo_extraccion="manual",
    ))
    candidates = [{"id": 1, "articulo_id": a_id, "id_norma": "DECRETO_10", "score": 0.5}]
    boosted = graph_boost(candidates, query_concepts=["COMA"])
    assert boosted[0]["score"] > 0.5
    assert "graph_boost_factor" in boosted[0]


@pytest.mark.integration
def test_hierarchical_expand_loads_parent_text(db_clean):
    from src.components.vectorstore import PostgresStore
    from src.core.models import Norma, Articulo, Fragmento
    from src.pipelines.retrieve import hierarchical_expand
    s = PostgresStore()
    s.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="X"))
    aid = s.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="ARTICULO COMPLETO " * 50))
    s.upsert_fragmento(Fragmento(articulo_id=aid, chunk_index=0,
        text="frag1", contextual_text="ctx1", embedding=[0.0]*1024))
    s.upsert_fragmento(Fragmento(articulo_id=aid, chunk_index=1,
        text="frag2", contextual_text="ctx2", embedding=[0.0]*1024))
    candidates = [
        {"id": 1, "articulo_id": aid, "score": 0.9},
        {"id": 2, "articulo_id": aid, "score": 0.8},
    ]
    expanded = hierarchical_expand(candidates)
    assert len(expanded) == 1
    assert "ARTICULO COMPLETO" in expanded[0]["articulo_text"]
    assert expanded[0]["articulo_id"] == aid


@pytest.mark.integration
def test_simple_retriever_end_to_end_with_mock(db_clean):
    """Smoke: ingest a fragment via mocks, retrieve gives back results."""
    from unittest.mock import MagicMock
    from src.components.vectorstore import PostgresStore
    from src.core.models import Norma, Articulo, Fragmento
    from src.pipelines.retrieve import SimpleRetriever
    s = PostgresStore()
    s.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="X"))
    aid = s.upsert_articulo(Articulo(id_norma="X", numero="1°",
                                     texto="potencia firme calculo metodologia"))
    s.upsert_fragmento(Fragmento(articulo_id=aid, chunk_index=0,
        text="potencia firme calculo",
        contextual_text="potencia firme calculo metodologia",
        embedding=[0.5]*1024))
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.5]*1024]
    fake_reranker = MagicMock()
    fake_reranker.rerank.side_effect = lambda q, docs, top_k: [
        (i, 1.0/(i+1)) for i in range(min(len(docs), top_k))
    ]

    rr = SimpleRetriever(store=s, embedder=fake_embedder, reranker=fake_reranker)
    results = rr.retrieve("potencia firme", top_k=5)
    assert len(results) >= 1
    assert "articulo_text" in results[0]


@pytest.mark.integration
def test_complex_retriever_smoke(db_clean):
    """Smoke test: ComplexRetriever runs end-to-end with mocked LLM and reranker."""
    from unittest.mock import MagicMock
    from src.components.vectorstore import PostgresStore
    from src.core.models import Norma, Articulo, Fragmento
    from src.pipelines.retrieve import ComplexRetriever
    s = PostgresStore()
    s.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="X"))
    aid = s.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="potencia firme texto"))
    s.upsert_fragmento(Fragmento(articulo_id=aid, chunk_index=0,
        text="potencia firme", contextual_text="potencia firme calculo",
        embedding=[0.5]*1024))

    fake_emb = MagicMock(); fake_emb.embed.return_value = [[0.5]*1024]
    fake_rr = MagicMock()
    fake_rr.rerank.side_effect = lambda q, docs, top_k: [(i, 1.0/(i+1)) for i in range(min(len(docs), top_k))]
    fake_llm = MagicMock()
    fake_llm.generate.return_value = MagicMock(text="generated", tokens_in=1, tokens_out=1)

    cr = ComplexRetriever(store=s, embedder=fake_emb, reranker=fake_rr, llm=fake_llm)
    results = cr.retrieve("potencia firme", top_k=5)
    assert len(results) >= 1
    assert "articulo_text" in results[0]


def test_adaptive_retriever_uses_simple_for_short_query():
    """Unit test: AdaptiveRetriever calls SimpleRetriever for simple-classified queries."""
    from unittest.mock import MagicMock
    from src.pipelines.retrieve import AdaptiveRetriever

    simple = MagicMock(); simple.retrieve.return_value = [{"id": 1}]
    complejo = MagicMock()
    router = MagicMock(); router.classify.return_value = "simple"

    ar = AdaptiveRetriever(simple=simple, complejo=complejo, router=router)
    branch, results = ar.retrieve("¿qué es COMA?", top_k=5)
    assert branch == "simple"
    assert len(results) == 1
    simple.retrieve.assert_called_once()
    complejo.retrieve.assert_not_called()
