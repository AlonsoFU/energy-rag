"""Definitoriedad scoring — GENERAL, semantic, no phrasing.

Replaces the brittle `se entenderá por:` regex as the way to tell which article
DEFINES a concept. Each candidate article is scored by semantic similarity
between a neutral definitional probe for the concept ("qué es <nombre>") and the
article text, using the same embedder the retriever uses. This generalises to
ANY wording — constitutive ("la X será una persona jurídica…"), methodological
("el A.V.I. se determinará a partir de…") or glossary ("se entenderá por…") —
without a list of accepted phrasings.

The score only RANKS candidates (fuzzy, to UNDERSTAND which article to look at);
the final pick is still decided by the legal criteria / human confirmation
(exact, to ANSWER). `embed_fn` is injected so this is testable on CPU.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

EmbedFn = Callable[[list[str]], Sequence[Sequence[float]]]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return num / (na * nb)


def _probe(nombre: str) -> str:
    """Neutral definitional intent applied uniformly to every concept.

    This is the question the system answers, not a phrasing of how definitions
    are written in the corpus, so it stays concept- and wording-agnostic.
    """
    return f"qué es {nombre}: definición"


def score_definitoriedad(nombre: str, candidates: list[dict],
                         embed_fn: EmbedFn) -> list[dict]:
    """Add `def_score` (cosine vs the definitional probe) to each candidate.

    Returns the same list ordered by `def_score` descending. Candidates without
    text get score 0.0. Mutates the dicts in place (adds `def_score`).
    """
    if not candidates:
        return candidates
    texts = [_probe(nombre)] + [(c.get("definicion") or "") for c in candidates]
    vecs = embed_fn(texts)
    qv = vecs[0]
    for c, v in zip(candidates, vecs[1:]):
        c["def_score"] = _cosine(qv, v)
    candidates.sort(key=lambda c: c.get("def_score", 0.0), reverse=True)
    return candidates
