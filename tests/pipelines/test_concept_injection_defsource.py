from src.pipelines import concept_injection as ci


def test_definition_source_pointer_present():
    md = {"definition_source": {"id_norma": "29819", "articulo": "23",
                                "confianza": "baja", "needs_review": True}}
    assert ci.definition_source_pointer(md) == ("29819", "23")


def test_definition_source_pointer_absent():
    assert ci.definition_source_pointer({}) is None
    assert ci.definition_source_pointer(None) is None


def test_definition_source_used_even_if_low_confidence(monkeypatch):
    # Low-confidence (needs_review) pointer is still used by inject.
    monkeypatch.setattr(ci, "_concept_index", lambda: {
        "sec": ("29819", "23", "entidad que sucedió legalmente…",
                "Superintendencia de Electricidad y Combustibles"),
    })
    out = ci.inject_definition("qué es SEC", [])
    assert out[0]["id_norma"] == "29819" and out[0]["articulo_numero"] == "23"
