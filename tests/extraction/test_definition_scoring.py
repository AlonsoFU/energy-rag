"""Definitoriedad scoring is semantic and general (no phrasing whitelist)."""
from src.extraction.definition_scoring import score_definitoriedad


def _fake_embed(texts):
    """Toy embedder: a text's vector counts [substance_markers, name_echo].

    Substantive definitions ("será una persona jurídica", "se determinará a
    partir de") score on dim 0; bare labels echoing the name score on dim 1.
    The probe asks for substance, so substantive candidates rank first —
    regardless of the exact wording.
    """
    out = []
    for t in texts:
        tl = t.lower()
        substance = sum(k in tl for k in
                        ("persona jurídica", "se determinará", "naturaleza", "definición"))
        echo = 1.0 if "etiqueta" in tl else 0.0
        out.append([float(substance), echo])
    return out


def test_substantive_outranks_label_regardless_of_phrasing():
    cands = [
        {"id_norma": "A", "articulo": "1", "definicion": "Concepto: etiqueta"},
        {"id_norma": "B", "articulo": "6", "definicion": "La X será una persona jurídica de derecho público"},
        {"id_norma": "C", "articulo": "48", "definicion": "El valor se determinará a partir de su base"},
    ]
    ranked = score_definitoriedad("X", cands, _fake_embed)
    assert ranked[0]["id_norma"] in ("B", "C")
    assert ranked[-1]["id_norma"] == "A"
    assert all("def_score" in c for c in ranked)


def test_empty_candidates_noop():
    assert score_definitoriedad("X", [], _fake_embed) == []
