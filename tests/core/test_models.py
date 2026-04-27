from datetime import date
from src.core.models import Norma, Articulo, Fragmento, Concepto, Referencia


def test_norma_minimal():
    n = Norma(id_norma="DECRETO_62", tipo="DECRETO", numero="62", titulo="Reglamento...")
    assert n.id_norma == "DECRETO_62"
    assert n.clase is None


def test_articulo_requires_norma():
    a = Articulo(id_norma="DECRETO_62", numero="1°", texto="Artículo primero...")
    assert a.numero == "1°"


def test_fragmento_with_embedding():
    f = Fragmento(
        articulo_id=1, chunk_index=0,
        text="raw", contextual_text="ctx + raw",
        embedding=[0.1] * 768,
    )
    assert len(f.embedding) == 768


def test_referencia_xor_origen():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Referencia(
            tipo_relacion="cita",
            confianza=0.9,
            metodo_extraccion="regex",
            origen_articulo_id=1,
            origen_norma_id="X",  # both set -> invalid
            destino_norma_id="Y",
        )
