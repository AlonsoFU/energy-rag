"""Merge curated and retrieval-gathered definition candidates.

`curated` come from `define_termino` edges (trusted). `retrieved` come from
corpus search (fuzzy). Each result is tagged `origin` so downstream layers can
treat them differently: the deterministic resolver uses only curated; the
tentative LLM proposer sees both. Dedup by (id_norma, articulo), curated wins.
"""
from __future__ import annotations


def gather_candidates(curated: list[dict], retrieved: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for c in curated:
        key = (str(c["id_norma"]), str(c["articulo"]))
        seen.add(key)
        out.append({**c, "origin": "curated"})
    for c in retrieved:
        key = (str(c["id_norma"]), str(c["articulo"]))
        if key in seen:
            continue
        seen.add(key)
        out.append({**c, "origin": "retrieved"})
    return out
