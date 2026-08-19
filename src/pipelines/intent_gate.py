"""GATE de intención: ¿esta query pide una DEFINICIÓN? — clasificador, no regex.

`glossary_lookup` extrae bien el término, pero no decide **si corresponde inyectar**. Sin gate
contamina lo operativo: sobre `queries_complex_v3` dispara 20/51 y sobre el holdout 7/19, porque
"Cliente", "Ley", "Comisión", "Coordinador" son términos del glosario que aparecen en cualquier
pregunta. Este módulo es ese gate.

Regresión logística sobre el embedding de la query (`qwen3-embedding:4b`, MRL-1024, el mismo del
retrieval). Los coeficientes se entrenan con `scripts/train_intent_gate.py` y viven en
`data/intents/gate_definicion_v1.json`; acá solo hay un producto punto — sin sklearn en runtime.

Medido fuera de muestra (`queries_fraseos_v1` nunca entró al train):

    inyecciones          fraseos_v1(+)   complex_v3(-)   holdout op.(-)
    hoy (regex)                0/64            0/51             0/19
    diccionario solo          54/64           20/51             7/19
    gate + diccionario        52/64            0/51             0/19

Cuesta 2 inyecciones correctas y elimina las 27 indebidas.

ESCALA: costo por query = 1 embedding (reusa el del retrieval si está cacheado) + un producto
punto de 1024 dims. Constante respecto al tamaño del corpus. Reentrenar al agregar intenciones
o al cambiar de embedder — los coeficientes son específicos del espacio vectorial.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

MODELO = Path("data/intents/gate_definicion_v1.json")


@lru_cache(maxsize=1)
def _modelo():
    if not MODELO.exists():
        return None
    d = json.loads(MODELO.read_text())
    return d["coef"], d["intercept"], d["dim"]


@lru_cache(maxsize=512)
def _emb(text: str):
    from src.pipelines.retrieve import _embed_4b_query
    return tuple(_embed_4b_query(text) or ())


def score(query: str) -> float | None:
    """Logit del clasificador. None si no hay modelo o falla el embedding."""
    m = _modelo()
    if not m:
        return None
    coef, b, dim = m
    v = _emb(query or "")
    if len(v) < dim:
        return None
    v = v[:dim]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return sum(c * (x / n) for c, x in zip(coef, v)) + b


def is_definition(query: str, default: bool = True) -> bool:
    """True si la query pide una definición. `default` se usa si el gate no puede opinar."""
    s = score(query)
    return default if s is None else s > 0.0
