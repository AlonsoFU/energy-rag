"""Select the authoritative defining article among candidates.

Rule (B1, refined 2026-05-28 per user — "lo que dice la jerarquía chilena"):

Chilean norm hierarchy: LEY ≡ DFL ≡ DL > DECRETO > RESOLUCIÓN. Two doctrines
combine, and they apply at DIFFERENT scopes:

  - *lex SUPERIOR* governs ACROSS tiers: a higher-tier norm always prevails. A
    reglamento (DECRETO) only implements/details the law and can never derogate
    or override it (tacit derogation, CC art. 52-53, requires equal-or-higher
    rank). So recency is IRRELEVANT across tiers: a newer DECRETO does NOT beat
    an older LEY.
  - *lex POSTERIOR* (newer wins) operates only WITHIN a tier, and only when the
    context (ámbito) is the same. We cannot detect ámbito, so among same-tier
    peers we do NOT guess.

Therefore:
  - single candidate → resolved.
  - exactly ONE norma holds the top tier → it strictly outranks every other
    candidate (all lower tier) → lex superior → resolved (recency ignored).
    Among that norma's own articles, the most-recent/last wins.
  - TWO+ distinct normas share the top tier → same-tier peers, ámbito may differ
    → CONFLICT → ask the user (B3 UX). E.g. Panel de Expertos in DECRETO 10/2019
    (Valorización) vs DECRETO 37/2021 (Transmisión).

Derogation/vigencia (B2) and explicit ámbito derivation are deferred.
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
    # Articles at the top tier, most-recent first (for same-norma article choice).
    top = sorted((c for c in candidates if c["rank"] == best_rank),
                 key=_recency, reverse=True)

    # TWO+ distinct normas share the top tier → same-tier peers. lex posterior
    # only holds within the same ámbito, which we cannot detect → ask. (Panel:
    # DECRETO 10/2019 Valorización vs DECRETO 37/2021 Transmisión.)
    if len({c["id_norma"] for c in top}) > 1:
        return _conflict(top)

    # Exactly ONE norma holds the top tier → it strictly outranks every other
    # candidate (all lower tier). lex SUPERIOR governs across tiers; recency
    # (lex posterior) does not cross tiers, so a newer subordinate norm cannot
    # displace it. Resolve to it; its most-recent article wins (top is sorted).
    w = top[0]
    return {"status": "resolved", "id_norma": w["id_norma"], "articulo": w["articulo"]}
