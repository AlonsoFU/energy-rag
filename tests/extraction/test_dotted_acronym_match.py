"""Whole-term matching must work for dotted acronyms (A.V.I., V.A.T.T.)
without matching partial words — the bug that left tariff acronyms edgeless."""
from src.extraction.regex_refs import whole_term_pattern
from src.extraction.concept_refs import extract_concept_refs


def test_dotted_acronym_now_matches():
    p = whole_term_pattern("A.V.I.")
    assert p.search("El A.V.I. de las instalaciones se determinará")
    assert p.search("compuesto por la suma del A.V.I. y el C.O.M.A.")


def test_dotted_acronym_matches_at_end():
    assert whole_term_pattern("V.A.T.T.").search("el menor V.A.T.T.")


def test_plain_word_still_rejects_partial():
    # 'COMA' must not match inside 'COMARCA' (whole-term behavior preserved)
    assert not whole_term_pattern("COMA").search("la COMARCA vecina")
    assert whole_term_pattern("COMA").search("el COMA anual")


def test_concept_refs_links_dotted_acronym():
    refs = extract_concept_refs(
        "El A.V.I. se determinará a partir de su V.I.",
        origen_articulo_id=1, origen_norma_id="X",
        conceptos=[{"id": 264, "nombre": "A.V.I.", "aliases": None}],
    )
    assert [r.destino_concepto_id for r in refs] == [264]
