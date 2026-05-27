from src.pipelines import concept_injection as ci


def test_definition_source_pointer_confirmed_is_injected():
    # High-confidence / confirmed pointer (needs_review False) → injected.
    md = {"definition_source": {"id_norma": "29819", "articulo": "23",
                                "confianza": "alta", "needs_review": False}}
    assert ci.definition_source_pointer(md) == ("29819", "23")


def test_definition_source_pointer_needs_review_is_gated():
    # GATE (2026-05-26): a tentative (needs_review) pointer is NOT injected;
    # retrieval answers until a human/skill confirms it.
    md = {"definition_source": {"id_norma": "29819", "articulo": "23",
                                "confianza": "baja", "needs_review": True}}
    assert ci.definition_source_pointer(md) is None


def test_definition_source_pointer_absent():
    assert ci.definition_source_pointer({}) is None
    assert ci.definition_source_pointer(None) is None


def test_confirmed_source_used_by_inject(monkeypatch):
    # A confirmed (needs_review False) source flows through inject_definition.
    monkeypatch.setattr(ci, "_concept_index", lambda: {
        "sec": ("29819", "2", "objeto de la SEC…",
                "Superintendencia de Electricidad y Combustibles"),
        "superintendencia de electricidad y combustibles": (
            "29819", "2", "objeto de la SEC…",
            "Superintendencia de Electricidad y Combustibles"),
    })
    monkeypatch.setattr(ci, "_all_concepts", lambda: [
        {"nombre": "Superintendencia de Electricidad y Combustibles",
         "aliases": ["SEC"]},
    ])
    out = ci.inject_definition("qué es SEC", [])
    assert out[0]["id_norma"] == "29819" and out[0]["articulo_numero"] == "2"
