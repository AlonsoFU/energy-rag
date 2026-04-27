from src.extraction.regex_refs import extract_regex_refs
from src.core.catalogo import Catalogo, NormaEntry

CATALOGO = Catalogo([
    NormaEntry(id_canonico="DECRETO_62", tipo="DECRETO", numero="62", año=2006,
               variantes=["D.S. N° 62", "D.S. 62", "Decreto Supremo 62"]),
    NormaEntry(id_canonico="LEY_20936", tipo="LEY", numero="20936",
               variantes=["Ley N° 20.936", "Ley 20.936", "Ley 20936"]),
    NormaEntry(id_canonico="DFL_4", tipo="DFL", numero="4", año=1982,
               variantes=["DFL N° 4", "DFL 4", "D.F.L. 4"]),
])


def test_articulo_de_norma_match():
    refs = extract_regex_refs("Según el artículo 5° del D.S. N° 62 se establece...", CATALOGO)
    assert len(refs) == 1
    assert refs[0].destino_norma_id == "DECRETO_62"
    assert refs[0].metadata.get("articulo_numero") == "5"
    assert refs[0].confianza >= 0.85


def test_norma_alone_match():
    refs = extract_regex_refs("Conforme a la Ley N° 20.936, las empresas...", CATALOGO)
    assert any(r.destino_norma_id == "LEY_20936" for r in refs)


def test_subdivision_captured():
    refs = extract_regex_refs("la letra b) del artículo 5 del DFL 4", CATALOGO)
    assert any(r.destino_subdivision and "letra b" in r.destino_subdivision.lower() for r in refs)


def test_unknown_norm_skipped():
    refs = extract_regex_refs("según la Ley 99.999", CATALOGO)
    assert refs == []


def test_multiple_refs_in_text():
    text = "El artículo 5° del D.S. 62 se complementa con el artículo 12 del DFL 4."
    refs = extract_regex_refs(text, CATALOGO)
    assert len(refs) == 2
