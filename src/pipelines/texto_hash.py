"""Hash ESTABLE del texto de una norma — para detectar cambios NORMATIVOS, no cosméticos.

`normas.metadata.content_hash` es un sha256 del texto CRUDO que baja el crawler. Como detector
de cambios es inservible: cambia con cualquier espacio, salto de línea o pedazo de interfaz que
BCN mueva. Medido re-bajando las 25 normas modificadas:

    13 de 25 acusaron "texto_modificado"  ->  al comparar el contenido, TODAS eran cosméticas
    LEY 20365   28.952 -> 28.952 chars, similitud 1.0000, 0 bloques distintos
    LEY 20410   71.100 -> 71.119 chars, similitud 0.9999, única diferencia ' Ley Historia de la'

Un monitor que avisa cada semana porque BCN movió un espacio no lo lee nadie. Este módulo
normaliza antes de hashear:

  - colapsa todo el espacio en blanco (incluido `\\xa0`, que BCN usa mucho)
  - saca el chrome de la pagina que se cuela en `innerText`
  - baja a minúsculas y quita tildes: un cambio de tipografía no es un cambio normativo

Lo que SÍ sobrevive a la normalización: agregar/quitar/reemplazar texto del articulado, que es
exactamente lo que se quiere detectar.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# fragmentos de interfaz de BCN que aparecen y desaparecen del innerText sin que
# cambie la norma. Se sacan ANTES de hashear.
_CHROME = re.compile(
    r"(ley\s+historia\s+de\s+la|volver\s+arriba|comparar\s+versiones|imprimir|"
    r"descargar|compartir|ingresar|regist(?:rarse|rese)|pol[ií]tica\s+de\s+privacidad|"
    r"t[ée]rminos\s+del\s+servicio|biblioteca\s+del\s+congreso\s+nacional|loading)",
    re.I)


def normalizar(texto: str) -> str:
    """Texto comparable: sin tildes, minúsculas, espacio colapsado, sin chrome de BCN."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    t = t.replace("\xa0", " ")
    t = _CHROME.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def hash_estable(texto: str) -> str:
    """sha256[:16] del texto normalizado. Reemplaza a `content_hash` para comparar versiones."""
    return hashlib.sha256(normalizar(texto).encode()).hexdigest()[:16]


# Un cambio normativo real agrega, quita o reemplaza articulado: mueve el texto en varios
# por mil, no en unas pocas palabras. Perseguir cada variante del chrome de BCN con una lista
# es una carrera perdida -- ya se escapo "historia de la ley" (la lista tenia el mismo texto
# en otro orden), "jurisprudencia" y "anotese, tomese razon y publiquese".
UMBRAL_SIMILITUD = 0.995
# ⚠️ El umbral supone textos LARGOS (normas de miles de caracteres), que es el caso real:
# ahi el chrome de BCN pesa por mil. En un texto de 80 caracteres, 60 de chrome hunden la
# similitud a 0.70 y el filtro no aplica. No usar `cambio_real` para fragmentos cortos.


def similitud(viejo: str, nuevo: str) -> float:
    """Cuanto se parecen dos versiones tras normalizar. 1.0 = identicas."""
    import difflib
    return difflib.SequenceMatcher(None, normalizar(viejo), normalizar(nuevo)).ratio()


def cambio_real(viejo: str, nuevo: str, umbral: float = UMBRAL_SIMILITUD) -> bool:
    """True solo si el contenido normativo difiere de verdad.

    Dos filtros en cascada: primero el hash normalizado (barato); si difiere, se mide la
    similitud, porque el hash cambia con una sola palabra. Medido sobre los 13 eventos que
    el monitor habia registrado: TODOS tenian similitud >= 0.9977 y su unica diferencia era
    texto de interfaz de BCN.
    """
    if hash_estable(viejo) == hash_estable(nuevo):
        return False
    return similitud(viejo, nuevo) < umbral
