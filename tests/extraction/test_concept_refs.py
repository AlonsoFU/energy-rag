from src.extraction.concept_refs import extract_concept_refs


def test_concept_mention_creates_reference():
    """Cuando un texto menciona 'COMA' y existe concepto 'COMA' en DB,
    se crea una referencia origen->concepto_id."""
    conceptos = [{"id": 1, "nombre": "COMA", "aliases": []}]
    refs = extract_concept_refs(
        text="Las empresas calculan el COMA de cada mes según...",
        origen_articulo_id=10, origen_norma_id="DECRETO_X",
        conceptos=conceptos,
    )
    assert len(refs) == 1
    assert refs[0].destino_concepto_id == 1
    assert refs[0].tipo_relacion in ("aplica", "menciona", "cita")
    assert refs[0].origen_articulo_id == 10


def test_alias_match():
    conceptos = [{"id": 2, "nombre": "potencia firme", "aliases": ["potencia firme inicial"]}]
    refs = extract_concept_refs(
        text="La potencia firme inicial se calcula así",
        origen_articulo_id=10, origen_norma_id="X",
        conceptos=conceptos,
    )
    assert refs[0].destino_concepto_id == 2


def test_no_match():
    conceptos = [{"id": 1, "nombre": "COMA", "aliases": []}]
    refs = extract_concept_refs(text="texto sin conceptos",
        origen_articulo_id=1, origen_norma_id="X", conceptos=conceptos)
    assert refs == []
