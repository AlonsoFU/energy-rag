import pytest
from src.storage.connection import with_connection
from src.components.vectorstore import PostgresStore
from src.core.models import Norma, Articulo, Concepto


@pytest.mark.integration
def test_embed_all_processes_articulos(db_clean):
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="Ley X"))
    store.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="texto del artículo " * 30))
    store.upsert_articulo(Articulo(id_norma="X", numero="2°", texto="otro texto " * 30))

    from scripts.embed_all import run_embed_all
    stats = run_embed_all(skip_contextual=True, mock=True, limit=None, skip_references=True)
    assert stats["articulos_processed"] == 2
    assert stats["fragmentos_created"] >= 2  # at least one chunk each

    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM fragmentos")
        assert cur.fetchone()[0] >= 2


@pytest.mark.integration
def test_embed_all_with_limit(db_clean):
    """--limit 1 should process only 1 articulo."""
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="Ley X"))
    for i in range(3):
        store.upsert_articulo(Articulo(id_norma="X", numero=f"{i+1}°", texto=f"texto {i}" * 30))

    from scripts.embed_all import run_embed_all
    stats = run_embed_all(skip_contextual=True, mock=True, limit=1, skip_references=True)
    assert stats["articulos_processed"] == 1


@pytest.mark.integration
def test_embed_all_extracts_references_when_enabled(db_clean):
    """When skip_references=False, extract_references_for_articulo runs and populates referencias."""
    from scripts.embed_all import run_embed_all

    store = PostgresStore()
    # Two normas so cross-references can resolve
    store.upsert_norma(Norma(id_norma="DFL_4", tipo="DFL", numero="4", titulo="LGSE"))
    store.upsert_norma(Norma(
        id_norma="DECRETO_62", tipo="DECRETO", numero="62",
        titulo="Reglamento Transferencias",
    ))
    store.upsert_articulo(Articulo(
        id_norma="DECRETO_62", numero="1°", orden=0,
        texto="Conforme al artículo 5° del DFL N° 4 y a lo establecido en la LGSE.",
    ))
    store.upsert_concepto(Concepto(nombre="COMA", definicion="d", aliases=[]))
    # An articulo mentioning the concept
    store.upsert_articulo(Articulo(
        id_norma="DFL_4", numero="1°", orden=0,
        texto="El cálculo del COMA se realizará anualmente.",
    ))

    stats = run_embed_all(skip_contextual=True, mock=True, limit=None, skip_references=False)
    assert stats["referencias_created"] > 0

    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM referencias")
        n = cur.fetchone()[0]
        assert n > 0
