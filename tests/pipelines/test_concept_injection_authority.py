from src.pipelines import concept_injection as ci


def test_authoritative_pointer_present():
    md = {"authoritative": {"id_norma": "1183783", "articulo": "2"}}
    assert ci.authoritative_pointer(md) == ("1183783", "2")


def test_authoritative_pointer_absent():
    assert ci.authoritative_pointer({}) is None
    assert ci.authoritative_pointer(None) is None
    assert ci.authoritative_pointer({"authoritative": None}) is None


def test_authoritative_pointer_conflict_not_forced():
    # A conflict is NOT auto-resolved: inject falls back to fecha behaviour (B3 UX).
    md = {"authoritative": None,
          "authority_conflict": [{"id_norma": "A", "articulo": "1"}]}
    assert ci.authoritative_pointer(md) is None


def test_inject_uses_authoritative_article(monkeypatch):
    # Index resolves the alias "sec" to the AUTHORITATIVE LEY article (1183783),
    # not a fecha-based decreto. inject must cite that article.
    monkeypatch.setattr(ci, "_concept_index", lambda: {
        "sec": ("1183783", "2",
                "la Superintendencia de Electricidad y Combustibles.",
                "Superintendencia de Electricidad y Combustibles"),
    })
    out = ci.inject_definition("qué es SEC", [])
    assert out[0]["id_norma"] == "1183783"
    assert out[0]["articulo_numero"] == "2"
