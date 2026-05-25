"""Capa 1 — deterministic choice of the authoritative defining article.

Among candidates for a concept: keep the SUBSTANTIVE ones (drop labels), then
apply the legal antinomy criteria reused from B1 (jerarquía → fecha). If a
single substantive candidate or a clear rank/date winner exists → resolved
(high confidence). If rank disagrees with recency (possible different context,
per the B1 refinement) or there is no substantive candidate → unresolved, so
the residue goes to the tentative proposer (Capa 2).
"""
from __future__ import annotations

from src.extraction.authority import select_authoritative
from src.extraction.definition_quality import is_label


def _substantive(name: str, cands: list[dict]) -> list[dict]:
    return [c for c in cands if not is_label(name, c.get("definicion", ""))]


def resolve_definition_source(nombre: str, candidates: list[dict]) -> dict:
    # Deterministic layer trusts ONLY curated (define_termino) candidates; cita
    # mentions and retrieved (fuzzy) ones are left for the tentative proposer
    # (legal-safety: no high-confidence auto-resolve on non-definitional sources).
    curated = [c for c in candidates if c.get("origin", "curated") == "curated"]
    subs = _substantive(nombre, curated)
    if not subs:
        return {"status": "unresolved", "reason": "no-substantive-candidate"}
    if len(subs) == 1:
        w = subs[0]
        return {"status": "resolved", "id_norma": w["id_norma"],
                "articulo": w["articulo"], "confianza": "alta",
                "criterio": "sustancia"}
    # >1 substantive: defer the rank/date/context decision to B1's resolver,
    # which only resolves when rank and recency agree (else conflict → ask).
    auth = select_authoritative([
        {"id_norma": c["id_norma"], "articulo": c["articulo"],
         "rank": c["rank"], "fecha": c["fecha"]} for c in subs
    ])
    if auth["status"] != "resolved":
        return {"status": "unresolved", "reason": "rank-recency-conflict"}
    # Tag the criterion: unique top rank → jerarquía; otherwise fecha broke the tie.
    best_rank = max(c["rank"] for c in subs)
    top = [c for c in subs if c["rank"] == best_rank]
    criterio = "jerarquia" if len(top) == 1 else "fecha"
    return {"status": "resolved", "id_norma": auth["id_norma"],
            "articulo": auth["articulo"], "confianza": "alta",
            "criterio": criterio}
