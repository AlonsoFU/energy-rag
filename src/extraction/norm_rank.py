"""Derive a norm's legal rank from its TITLE (not the unreliable `tipo`).

LEY ≡ DFL ≡ DL (legal) > DECRETO/DS > RESOLUCIÓN. Verified: CPR art. 64
(DFL has fuerza de ley). The `tipo` column is mislabeled in the data (e.g. a
RESOLUCION tagged LEY, a DL tagged "Ley"), so the title is authoritative; when
title and tipo disagree we flag for review. Refundido keeps the underlying rank.
"""
from __future__ import annotations
import re

LEGAL, DECRETO, RESOLUCION = 3, 2, 1
_T = lambda s: (s or "").upper()


def derive_rank(tipo: str, titulo: str) -> tuple[int, bool]:
    t = _T(titulo)
    # Title-driven rank (authoritative). Order matters: legal markers first.
    if re.search(r"\bDECRETO\s+LEY\b|\bD\.?L\.?\b", t) or \
       re.search(r"\bD\.?F\.?L\.?\b|FUERZA DE LEY", t):
        title_rank = LEGAL
    elif t.startswith("LEY") or re.search(r"\bLEY\s+N", t):
        title_rank = LEGAL
    elif "RESOLUCION" in t or "RESOLUCIÓN" in t:
        title_rank = RESOLUCION
    elif "DECRETO" in t:
        title_rank = DECRETO
    else:
        title_rank = None
    tipo_rank = {"LEY": LEGAL, "DFL": LEGAL, "DL": LEGAL,
                 "DECRETO": DECRETO, "RESOLUCIÓN": RESOLUCION,
                 "RESOLUCION": RESOLUCION}.get((tipo or "").upper())
    if title_rank is None:
        return (tipo_rank or DECRETO, True)        # not derivable → flag
    flagged = (tipo_rank is not None and tipo_rank != title_rank)
    return (title_rank, flagged)
