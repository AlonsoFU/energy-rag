import pytest
from src.components.vectorstore import PostgresStore
from src.core.models import Norma, Articulo, Fragmento, Concepto, Referencia


@pytest.mark.integration
def test_upsert_norma_and_get(db_clean):
    store = PostgresStore()
    n = Norma(id_norma="DECRETO_62", tipo="DECRETO", numero="62", titulo="Reglamento de transferencias")
    store.upsert_norma(n)
    nid = store.get_norma("DECRETO_62")
    assert nid is not None
    assert nid.titulo == "Reglamento de transferencias"


@pytest.mark.integration
def test_upsert_articulo_returns_id(db_clean):
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="DECRETO_62", tipo="DECRETO", numero="62", titulo="X"))
    a = Articulo(id_norma="DECRETO_62", numero="1°", texto="Artículo primero")
    art_id = store.upsert_articulo(a)
    assert isinstance(art_id, int)
    assert art_id > 0


@pytest.mark.integration
def test_upsert_fragmento_and_search_vector(db_clean):
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="DECRETO_62", tipo="DECRETO", numero="62", titulo="X"))
    aid = store.upsert_articulo(Articulo(id_norma="DECRETO_62", numero="1°", texto="x"))
    f = Fragmento(
        articulo_id=aid, chunk_index=0,
        text="potencia firme", contextual_text="ctx: potencia firme",
        embedding=[0.1] * 1024,  # 1024 dims (matches pgvector schema)
    )
    store.upsert_fragmento(f)
    results = store.search_vector([0.1] * 1024, top_k=5)
    assert len(results) == 1
    assert results[0]["contextual_text"] == "ctx: potencia firme"
    assert results[0]["id_norma"] == "DECRETO_62"


@pytest.mark.integration
def test_bm25_search(db_clean):
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="X"))
    aid = store.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="x"))
    store.upsert_fragmento(Fragmento(
        articulo_id=aid, chunk_index=0,
        text="raw", contextual_text="potencia firme inicial calculo",
        embedding=[0.0] * 1024,
    ))
    results = store.search_bm25("potencia firme", top_k=5)
    assert len(results) == 1


@pytest.mark.integration
def test_upsert_concepto_and_referencia(db_clean):
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="X"))
    aid = store.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="x"))
    cid = store.upsert_concepto(Concepto(nombre="COMA", definicion="d"))
    rid = store.upsert_referencia(Referencia(
        origen_articulo_id=aid,
        destino_concepto_id=cid,
        tipo_relacion="define_termino",
        confianza=1.0, metodo_extraccion="manual",
    ))
    assert isinstance(rid, int) and rid > 0
