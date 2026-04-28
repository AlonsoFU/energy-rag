import pytest
from src.core.catalogo import Catalogo, NormaEntry


@pytest.fixture
def catalogo_simple():
    entries = [
        NormaEntry(
            id_canonico="DFL_4", tipo="DFL", numero="4", año=1982,
            variantes=["DFL N° 4", "DFL 4", "D.F.L. 4"],
            aliases=["LGSE", "Ley General de Servicios Eléctricos"],
            titulo_oficial="DFL Nº 4 de 1982",
        ),
        NormaEntry(
            id_canonico="DECRETO_62", tipo="DECRETO", numero="62", año=2006,
            variantes=["D.S. N° 62", "Decreto Supremo 62", "decreto 62"],
            aliases=["Reglamento de Transferencias"],
            titulo_oficial="Decreto Supremo Nº 62 de 2006",
        ),
    ]
    return Catalogo(entries)


def test_resolve_alias(catalogo_simple):
    assert catalogo_simple.resolve("LGSE") == "DFL_4"
    assert catalogo_simple.resolve("la LGSE") == "DFL_4"
    assert catalogo_simple.resolve("Ley General de Servicios Eléctricos") == "DFL_4"


def test_resolve_variant(catalogo_simple):
    assert catalogo_simple.resolve("D.S. N° 62") == "DECRETO_62"
    assert catalogo_simple.resolve("Decreto Supremo 62") == "DECRETO_62"
    assert catalogo_simple.resolve("DFL 4") == "DFL_4"


def test_resolve_unknown(catalogo_simple):
    assert catalogo_simple.resolve("Ley 99999") is None


def test_resolve_normalizes_whitespace_and_case(catalogo_simple):
    assert catalogo_simple.resolve("  d.s.  N°  62  ") == "DECRETO_62"


def test_get_by_id(catalogo_simple):
    e = catalogo_simple.get("DECRETO_62")
    assert e.numero == "62"
