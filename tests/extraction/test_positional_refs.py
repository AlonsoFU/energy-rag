from src.extraction.positional_refs import extract_positional_refs


def test_articulo_precedente_links_to_previous():
    siblings = [
        {"id": 100, "orden": 4, "numero": "4°"},
        {"id": 101, "orden": 5, "numero": "5°"},
        {"id": 102, "orden": 6, "numero": "6°"},
    ]
    refs = extract_positional_refs(
        text="Según el artículo precedente, las empresas...",
        origen_articulo_id=101,
        origen_norma_id="DECRETO_X",
        siblings=siblings,
    )
    assert len(refs) == 1
    assert refs[0].destino_articulo_id == 100
    assert refs[0].origen_articulo_id == 101


def test_articulo_siguiente_links_to_next():
    siblings = [
        {"id": 100, "orden": 4, "numero": "4°"},
        {"id": 101, "orden": 5, "numero": "5°"},
        {"id": 102, "orden": 6, "numero": "6°"},
    ]
    refs = extract_positional_refs(
        text="Lo dispuesto en el artículo siguiente",
        origen_articulo_id=101, origen_norma_id="X",
        siblings=siblings,
    )
    assert refs[0].destino_articulo_id == 102


def test_first_articulo_has_no_precedente():
    siblings = [{"id": 100, "orden": 1, "numero": "1°"}]
    refs = extract_positional_refs(
        text="el artículo precedente", origen_articulo_id=100,
        origen_norma_id="X", siblings=siblings,
    )
    assert refs == []
