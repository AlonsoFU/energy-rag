import pytest
from unittest.mock import MagicMock

from src.pipelines.ingest import IngestPipeline
from src.core.models import Norma, Articulo
from src.storage.connection import with_connection


@pytest.mark.integration
def test_ingest_articulo_creates_fragmentos(db_clean):
    fake_embedder = MagicMock()
    fake_embedder.embed.return_value = [[0.1] * 1024]
    fake_enricher = MagicMock()
    fake_enricher.enrich.side_effect = lambda **kw: f"CTX: {kw['fragment_text']}"

    pipeline = IngestPipeline(embedder=fake_embedder, enricher=fake_enricher)
    n = Norma(id_norma="X", tipo="LEY", numero="1", titulo="X")
    pipeline.ingest_norma(n)
    a = Articulo(id_norma="X", numero="1°", texto="texto del artículo " * 100)
    pipeline.ingest_articulo(a, n)

    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM fragmentos")
        assert cur.fetchone()[0] >= 1
        cur.execute("SELECT contextual_text FROM fragmentos LIMIT 1")
        ct = cur.fetchone()[0]
        assert ct.startswith("CTX:")


@pytest.mark.integration
def test_extract_references_for_articulo_persists_referencias(db_clean):
    """Reference extraction over a small text persists Referencia rows in DB."""
    from src.core.catalogo import Catalogo, NormaEntry
    from src.components.vectorstore import PostgresStore
    fake_embedder = MagicMock()
    fake_enricher = MagicMock()
    catalogo = Catalogo([
        NormaEntry(id_canonico="DFL_4", tipo="DFL", numero="4",
                   variantes=["DFL N° 4", "DFL 4"], aliases=["LGSE"]),
    ])

    store = PostgresStore()
    store.upsert_norma(Norma(id_norma="X", tipo="LEY", numero="1", titulo="X"))
    store.upsert_norma(Norma(id_norma="DFL_4", tipo="DFL", numero="4", titulo="LGSE"))
    aid = store.upsert_articulo(Articulo(id_norma="X", numero="1°", texto="x"))

    pipeline = IngestPipeline(store=store, embedder=fake_embedder, enricher=fake_enricher,
                              catalogo=catalogo)
    n = pipeline.extract_references_for_articulo(
        articulo_id=aid,
        articulo_text="Conforme a la LGSE, las empresas...",
        origen_norma_id="X",
        siblings=[{"id": aid, "orden": 1, "numero": "1°"}],
        conceptos=[],
    )
    assert n == 1
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT destino_norma_id, metodo_extraccion FROM referencias")
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "DFL_4"
    assert rows[0][1] == "regex"
