import pytest
from src.storage.connection import with_connection
from src.components.vectorstore import PostgresStore
from src.core.models import Norma, Articulo


@pytest.mark.integration
def test_embed_all_processes_articulos(db_clean):
    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="Ley X"))
    store.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="texto del artículo " * 30))
    store.upsert_articulo(Articulo(id_norma="X", numero="2°", texto="otro texto " * 30))

    from scripts.embed_all import run_embed_all
    stats = run_embed_all(skip_contextual=True, mock=True, limit=None)
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
    stats = run_embed_all(skip_contextual=True, mock=True, limit=1)
    assert stats["articulos_processed"] == 1
