from pathlib import Path

import pytest

from src.descubrimiento.listado import leer_listado, leer_listado_con_descartes

FIXTURE = Path(__file__).parent.parent / "fixtures" / "bcn" / "obtxml_opt3_cantidad20.xml"


def _norma(id_norma="1", organismos=("ORG A",), fecha="2026-01-02", con_id=True):
    attr = f" idNorma='{id_norma}'" if con_id else ""
    orgs = "".join(f"<ORGANISMO>{o}</ORGANISMO>" for o in organismos)
    f = f"<FECHA_PUBLICACION>{fecha}</FECHA_PUBLICACION>" if fecha else ""
    return (
        f"<NORMA{attr}><TIPOS_NUMEROS><TIPO_NUMERO><TIPO>XX1</TIPO><NUMERO>7</NUMERO>"
        f"<DESCRIPCION>Resolución</DESCRIPCION></TIPO_NUMERO></TIPOS_NUMEROS>{f}"
        f"<TITULO>  UN   titulo </TITULO><ORGANISMOS>{orgs}</ORGANISMOS></NORMA>"
    )


def _xml(*normas):
    return ("<NORMAS>" + "".join(normas) + "</NORMAS>").encode("utf-8")


def test_fixture_real():
    pubs = leer_listado(FIXTURE.read_bytes())
    assert len(pubs) == 20
    for p in pubs:
        assert p.id_norma and p.numero and p.titulo and p.organismos
        assert p.tipo == "LEY"
        assert p.fecha_publicacion and len(p.fecha_publicacion) == 10
        assert p.url == f"https://www.bcn.cl/leychile/navegar?idNorma={p.id_norma}"


def test_primera_del_fixture():
    p = leer_listado(FIXTURE.read_bytes())[0]
    assert p.id_norma == "1228972"
    assert p.numero == "21841"
    assert p.organismos[0] == "MINISTERIO DE OBRAS PÚBLICAS"
    assert p.fecha_publicacion == "2026-10-09"


def test_dos_organismos_en_orden():
    pubs = leer_listado(_xml(_norma(organismos=("B", "A"))))
    assert pubs[0].organismos == ("B", "A")


def test_norma_sin_id_se_descarta():
    pubs, descartes = leer_listado_con_descartes(_xml(_norma(con_id=False), _norma("9")))
    assert [p.id_norma for p in pubs] == ["9"]
    assert descartes == 1


def test_sin_fecha():
    assert leer_listado(_xml(_norma(fecha=None)))[0].fecha_publicacion is None


def test_tipo_sin_tildes_y_titulo_colapsado():
    p = leer_listado(_xml(_norma()))[0]
    assert p.tipo == "RESOLUCION"
    assert p.titulo == "UN titulo"


def test_no_es_xml():
    with pytest.raises(ValueError):
        leer_listado(b"esto no es xml")
