"""Select the authoritative defining article among candidates.

Rule (B1): highest rank → most recent (lex posterior, NULLS last) → if still
tied, CONFLICT (do not guess). Derogation and ámbito are deferred (B2/ámbito).
"""
from __future__ import annotations


def select_authoritative(candidates: list[dict]) -> dict:
    if not candidates:
        return {"status": "empty"}
    best_rank = max(c["rank"] for c in candidates)
    top = [c for c in candidates if c["rank"] == best_rank]
    # Most recent among top rank; None dates sort last.
    top.sort(key=lambda c: (c["fecha"] is not None, c["fecha"] or ""), reverse=True)
    if len(top) > 1 and top[0]["fecha"] == top[1]["fecha"]:
        return {"status": "conflict",
                "candidates": [{"id_norma": c["id_norma"], "articulo": c["articulo"]}
                               for c in top]}
    w = top[0]
    return {"status": "resolved", "id_norma": w["id_norma"], "articulo": w["articulo"]}
