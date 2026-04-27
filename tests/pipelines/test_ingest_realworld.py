"""Edge cases in ingest pipeline using real-shaped fixtures."""
from src.pipelines.ingest import _to_referencia
from src.extraction.regex_refs import ExtractedRef


def test_to_referencia_drops_dual_origen():
    """When ExtractedRef has both origen_articulo_id and origen_norma_id set,
    _to_referencia should pick articulo_id (more specific)."""
    er = ExtractedRef(
        origen_articulo_id=100,
        origen_norma_id="X",
        destino_norma_id="Y",
        tipo_relacion="cita",
        confianza=0.9,
        metodo_extraccion="regex",
    )
    ref = _to_referencia(er)
    assert ref is not None
    assert ref.origen_articulo_id == 100
    assert ref.origen_norma_id is None


def test_to_referencia_falls_back_to_origen_norma():
    """No origen on ExtractedRef -> use the fallback norma."""
    er = ExtractedRef(
        destino_norma_id="Y",
        tipo_relacion="cita",
        confianza=0.9,
        metodo_extraccion="regex",
    )
    ref = _to_referencia(er, fallback_origen_norma="DECRETO_X")
    assert ref is not None
    assert ref.origen_norma_id == "DECRETO_X"


def test_to_referencia_returns_none_no_destino():
    """ExtractedRef with no destino -> cannot form valid Referencia."""
    er = ExtractedRef(
        origen_articulo_id=1,
        tipo_relacion="cita",
        confianza=0.9,
        metodo_extraccion="regex",
    )
    ref = _to_referencia(er)
    assert ref is None


def test_to_referencia_returns_none_multiple_destinos():
    """ExtractedRef with conflicting destinos -> cannot form valid Referencia."""
    er = ExtractedRef(
        origen_articulo_id=1,
        destino_norma_id="X",
        destino_concepto_id=5,
        tipo_relacion="cita",
        confianza=0.9,
        metodo_extraccion="regex",
    )
    ref = _to_referencia(er)
    assert ref is None
