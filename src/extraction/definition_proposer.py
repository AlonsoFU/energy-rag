"""Capa 2 — tentative (low-confidence) choice via the local LLM.

Only for the residue Capa 1 could not resolve. The LLM is asked to pick the
article that best DEFINES the concept, justified by a legal criterion
(jerarquía/fecha/especialidad/sustancia). The result is ALWAYS tentative
(`confianza="baja"`): the runner applies it but flags `needs_review`. Fails
open: bad/missing/out-of-set output → no proposal (the current mark stays).
"""
from __future__ import annotations

import json
from typing import Optional

from src.components.llm import LLMProvider, get_llm_provider

_SYSTEM = (
    "Eres un asistente jurídico. Te dan un concepto y varios artículos que lo "
    "definen. Elige el artículo que MEJOR define el concepto (el que dice qué ES, "
    "no el que sólo repite su nombre ni el que remite a otro). Considera, en orden, "
    "jerarquía de la norma, fecha (ley posterior) y especialidad (norma específica "
    "del organismo/materia). Responde SOLO un JSON: "
    '{"id_norma": "...", "articulo": "...", "criterio": '
    '"jerarquia|fecha|especialidad|sustancia", "fundamento": "..."}.'
)


def _candidates_block(cands: list[dict]) -> str:
    lines = []
    for c in cands:
        lines.append(
            f"- id_norma={c['id_norma']} articulo={c['articulo']} "
            f"rank={c['rank']} fecha={c['fecha']}: {c.get('definicion','')[:300]}")
    return "\n".join(lines)


def propose_definition_source(nombre: str, candidates: list[dict],
                              llm: Optional[LLMProvider] = None) -> dict:
    llm = llm or get_llm_provider()
    prompt = (f"Concepto: «{nombre}».\nCandidatos:\n"
              f"{_candidates_block(candidates)}\n\nElige uno.")
    try:
        raw = llm.generate(prompt=prompt, system=_SYSTEM, temperature=0.0).text
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except (ValueError, KeyError, json.JSONDecodeError):
        return {"status": "no-proposal"}
    allowed = {(str(c["id_norma"]), str(c["articulo"])) for c in candidates}
    pick = (str(data.get("id_norma")), str(data.get("articulo")))
    if pick not in allowed:
        return {"status": "no-proposal"}
    return {"status": "proposed", "id_norma": pick[0], "articulo": pick[1],
            "criterio": data.get("criterio", "llm"),
            "fundamento": data.get("fundamento", ""), "confianza": "baja"}
