"""Select the authoritative defining article among candidates.

Rule (B1, refined 2026-05-23 per user): different rank → the higher rank wins
(LEY > DECRETO …). BUT rank alone is not enough when context (ámbito) may differ:
the same term defined in a different-context norm can be a different concept. We
have no ámbito detection yet, so we only auto-resolve when we are SURE:

  - single candidate → resolved.
  - the rank winner is ALSO the most-recent overall → rank and recency agree,
    same-context lex-posterior → resolved.
  - otherwise (rank promotes an older/undated norm of possibly different context,
    OR a genuine same-rank+same-fecha tie) → CONFLICT → ask the user (B3 UX).

Derogation and explicit ámbito derivation are deferred (B2 / B-ámbito).
"""
from __future__ import annotations


def _recency(c: dict) -> tuple:
    # None dates sort last.
    return (c["fecha"] is not None, c["fecha"] or "")


def _conflict(cands: list[dict]) -> dict:
    return {"status": "conflict",
            "candidates": [{"id_norma": c["id_norma"], "articulo": c["articulo"]}
                           for c in cands]}


def select_authoritative(candidates: list[dict]) -> dict:
    if not candidates:
        return {"status": "empty"}
    if len(candidates) == 1:
        w = candidates[0]
        return {"status": "resolved", "id_norma": w["id_norma"], "articulo": w["articulo"]}

    best_rank = max(c["rank"] for c in candidates)
    top = sorted((c for c in candidates if c["rank"] == best_rank),
                 key=_recency, reverse=True)
    # Genuine tie within the top rank (same fecha) → ask.
    if len(top) > 1 and _recency(top[0]) == _recency(top[1]):
        return _conflict(top)

    rank_winner = top[0]
    recency_winner = sorted(candidates, key=_recency, reverse=True)[0]
    # Rank and recency agree → same-context lex-posterior, safe to resolve.
    if rank_winner["id_norma"] == recency_winner["id_norma"]:
        return {"status": "resolved", "id_norma": rank_winner["id_norma"],
                "articulo": rank_winner["articulo"]}
    # Higher rank but NOT the most recent → possible different context, not sure → ask.
    return _conflict([rank_winner, recency_winner])
