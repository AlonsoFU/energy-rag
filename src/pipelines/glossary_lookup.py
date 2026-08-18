"""Extracción del TÉRMINO por DICCIONARIO del glosario (reemplaza el regex de prefijo).

Motivo (exp #41/#42): `_definition_concept` extrae el concepto con un regex de PREFIJO
(`_DEF_PREFIX`), así que solo funciona con "qué es X" / "definición de X" / "qué significa X".
Con fraseos naturales la cobertura de `glossary_inject` es **0/64** — medido, no supuesto.

Este módulo invierte el planteamiento: en vez de preguntar *"¿cómo está fraseada la query?"*
pregunta *"¿qué término del glosario aparece en la query?"*. El glosario ya existe en la DB
(`fragmentos_definicion.termino`), así que es un dato, no una heurística.

Medido sobre `queries_fraseos_v1` (64 fraseos naturales, ninguno cubierto por el regex):

    regex de prefijo   .................  0/64
    diccionario         ................ 54/64  (control con fraseo cubierto: 53/64)

Reglas del match:
- por PALABRAS COMPLETAS, nunca subcadena (sin esto "AR" matchea dentro de "solares").
- gana el término MÁS LARGO (n-grama maximal), para que "Sistema de Transmisión Nacional"
  no pierda contra "Sistema".
- normalización: minúsculas, sin tildes, puntuación → espacio.

ESCALA: hoy 616 términos. A corpus completo serán ~10^5. El costo por query es
O(tokens²) lookups en un dict (una query de 12 palabras = 78 lookups), constante respecto
al tamaño del glosario; la memoria crece lineal (~5 MB por 100k términos). Lo que SÍ empeora
al escalar es la **ambigüedad**: más términos ⇒ más colisiones ⇒ el desempate de `def_exact`
(`ORDER BY length(texto) DESC`) pesa más. Ese es el frente G4 (entity resolution), no éste.
"""
from __future__ import annotations

import re
import unicodedata

_CACHE: dict[str, str] | None = None


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def _index(store) -> dict[str, str]:
    """{termino normalizado: termino original}. Se cachea por proceso."""
    global _CACHE
    if _CACHE is None:
        idx: dict[str, str] = {}
        for t in store.glossary_terms():
            k = _norm(t)
            if k:
                idx.setdefault(k, t)
        _CACHE = idx
    return _CACHE


def reset_cache() -> None:
    """Invalida el índice (tests, o tras reingestar el glosario)."""
    global _CACHE
    _CACHE = None


def find_term(query: str, store) -> str | None:
    """Término de glosario más largo presente en la query, o None. Sin regex de fraseo."""
    idx = _index(store)
    if not idx:
        return None
    toks = _norm(query).split()
    best: str | None = None
    for i in range(len(toks)):
        for j in range(len(toks), i, -1):
            k = " ".join(toks[i:j])
            if k in idx and (best is None or len(k) > len(best)):
                best = k
    return idx[best] if best else None
