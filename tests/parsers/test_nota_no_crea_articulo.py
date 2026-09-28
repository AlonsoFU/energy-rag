"""La nota marginal BCN no debe crear un articulo falso, tampoco llamando a _extract_articulos directo."""
from src.parsers.norm_structure_parser import NormStructureParser as P

CRUDO = ("     Artículo 222°.- El trazado de\nD.F.L. Nº 1, de\n1982, Minería\nArt. 147º\nD.O. 13.09.1982\n"
         " líneas aéreas por bienes nacionales de uso público deberá efectuarse de modo que no se poden los árboles.\n\n"
         "     Artículo 223°.- Otra disposición cualquiera del mismo cuerpo legal, suficientemente larga.\n")


def test_extract_directo_no_crea_fantasma():
    arts = P()._extract_articulos(CRUDO, [])
    claves = {k.replace("°", "").replace("º", "").strip() for k in arts}
    assert "147" not in claves, claves
    a222 = next(a for k, a in arts.items() if k.startswith("222"))
    assert "líneas aéreas" in a222.texto and "trazado" in a222.texto


def test_idempotente():
    limpio = P.quitar_notas_bcn(CRUDO)
    assert P.quitar_notas_bcn(limpio) == limpio
