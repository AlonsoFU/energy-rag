"""Capa 2 — tentative (low-confidence) choice via the local LLM.

Only for the residue Capa 1 could not resolve. The LLM is asked to pick the
article that best DEFINES the concept, justified by a legal criterion
(jerarquía/fecha/especialidad/sustancia). The result is ALWAYS tentative
(`confianza="baja"`): the runner applies it but flags `needs_review`. Fails
open: bad/missing/out-of-set output → no proposal (the current mark stays).
"""
from __future__ import annotations

import json
import re
from typing import Optional

from src.components.llm import LLMProvider, get_llm_provider

# A Chilean norm number written in prose: 3+ digits, optionally dotted
# ("20.936", "18.410", "2224"). Small integers (article numbers, days) and
# anything under 3 digits are ignored. General pattern, not concept-specific.
_NORM_NUM = re.compile(r"\b\d{1,3}(?:\.\d{3})+\b|\b\d{3,}\b")


def _norm_numbers(text: str) -> set[str]:
    return {m.group(0).replace(".", "") for m in _NORM_NUM.finditer(text or "")}


def _fundamento_consistent(fundamento: str, pick: dict) -> bool:
    """Anti-hallucination signal: does the justification cite the SAME norm it
    picked? Compares numbers cited in the fundamento against the numbers in the
    picked norm's TITLE (reliable) and `numero` field (often mislabeled, e.g.
    DL 2224 stored as 20776 — so the title is the source of truth). If the
    fundamento cites norm numbers but none matches → inconsistent.

    NOT used to reject (these picks are all needs_review anyway, and bad data
    would drop good picks); the runner annotates the inconsistency for the human.
    """
    cited = _norm_numbers(fundamento)
    if not cited:
        return True  # nothing to verify
    own = _norm_numbers(pick.get("titulo") or "")
    num = str(pick.get("numero") or "").replace(".", "")
    if num:
        own.add(num)
    if not own:
        return True  # can't verify against this norm
    return bool(cited & own)

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
        cuerpo = (c.get("texto") or c.get("definicion") or "")[:300]
        lines.append(
            f"- id_norma={c['id_norma']} articulo={c['articulo']} "
            f"rank={c['rank']} fecha={c['fecha']}: {cuerpo}")
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
    by_key = {(str(c["id_norma"]), str(c["articulo"])): c for c in candidates}
    pick = (str(data.get("id_norma")), str(data.get("articulo")))
    if pick not in by_key:
        return {"status": "no-proposal"}
    fundamento = data.get("fundamento", "")
    # Guard A (advisory, not a reject): flag a justification that argues about a
    # different norm than the one picked (the CNE "Ley 20.936" hallucination).
    consistent = _fundamento_consistent(fundamento, by_key[pick])
    return {"status": "proposed", "id_norma": pick[0], "articulo": pick[1],
            "criterio": data.get("criterio", "llm"),
            "fundamento": fundamento, "confianza": "baja",
            "fundamento_warning": not consistent}
