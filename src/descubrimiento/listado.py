"""Lee el listado de publicaciones de BCN (obtxml?opt=3) y lo convierte en Publicacion."""
import unicodedata
import xml.etree.ElementTree as ET

from src.descubrimiento.tipos import Publicacion

URL_NORMA = "https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"


def _texto(elemento: ET.Element | None) -> str:
    if elemento is None or elemento.text is None:
        return ""
    return " ".join(elemento.text.split())


def _mayusculas_sin_tildes(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFD", texto)
    sin_marcas = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
    return sin_marcas.upper()


def leer_listado_con_descartes(xml: bytes) -> tuple[list[Publicacion], int]:
    """Devuelve (publicaciones, cantidad de NORMA descartadas por no tener idNorma)."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError as e:
        raise ValueError(f"El listado de BCN no es XML valido: {e}") from e

    publicaciones: list[Publicacion] = []
    descartes = 0
    for norma in raiz.iter("NORMA"):
        id_norma = (norma.get("idNorma") or "").strip()
        if not id_norma:
            descartes += 1
            continue
        tipo_numero = norma.find("TIPOS_NUMEROS/TIPO_NUMERO")
        tipo = ""
        numero = ""
        if tipo_numero is not None:
            tipo = _mayusculas_sin_tildes(_texto(tipo_numero.find("DESCRIPCION")))
            numero = _texto(tipo_numero.find("NUMERO"))
        organismos = tuple(
            t for t in (o.text.strip() if o.text else "" for o in norma.findall("ORGANISMOS/ORGANISMO")) if t
        )
        fecha = _texto(norma.find("FECHA_PUBLICACION")) or None
        publicaciones.append(Publicacion(
            id_norma=id_norma,
            tipo=tipo,
            numero=numero,
            titulo=_texto(norma.find("TITULO")),
            organismos=organismos,
            fecha_publicacion=fecha,
            url=URL_NORMA.format(id_norma=id_norma),
        ))
    return publicaciones, descartes


def leer_listado(xml: bytes) -> list[Publicacion]:
    return leer_listado_con_descartes(xml)[0]
