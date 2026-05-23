# Resolución de autoridad (B1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]`.

**Goal:** Elegir la definición autoritativa (rango→fecha→flag) de términos definidos en >1 norma, determinista y legal-safe; corregir el ground-truth del eval.

**Architecture:** Dos funciones puras (`derive_rank`, `select_authoritative`) + un runner de ingesta (`resolve_authority.py`) que guarda un puntero `metadata.authoritative` por concepto; el inject lo usa; el generador del eval usa autoridad para el gold. Spec: `docs/superpowers/specs/2026-05-23-authority-resolution-design.md`.

**Tech Stack:** Python 3.12, psycopg, pytest. Bases verificadas: jerarquía CPR art.64, CC 52-53.

---

## Task 1: `derive_rank` (rango desde el título)

**Files:** Create `src/extraction/norm_rank.py`; Test `tests/extraction/test_norm_rank.py`

- [ ] **Step 1: Failing tests**

```python
from src.extraction.norm_rank import derive_rank, LEGAL, DECRETO, RESOLUCION

def test_dfl_is_legal_rank():
    assert derive_rank("DFL", "DFL 4 FIJA TEXTO REFUNDIDO…")[0] == LEGAL
def test_decreto_ley_is_legal_even_if_tipo_says_ley():
    rank, flagged = derive_rank("Ley", "DECRETO LEY 2224 CREA EL MINISTERIO")
    assert rank == LEGAL
def test_ley_is_legal():
    assert derive_rank("LEY", "LEY 18410 CREA LA SUPERINTENDENCIA")[0] == LEGAL
def test_decreto_is_regulatory():
    assert derive_rank("DECRETO", "DECRETO 37 APRUEBA REGLAMENTO")[0] == DECRETO
def test_resolucion_is_lowest():
    assert derive_rank("RESOLUCIÓN", "RESOLUCIÓN 711 EXENTA ESTABLECE")[0] == RESOLUCION
def test_mislabel_resolucion_tagged_ley_is_flagged():
    rank, flagged = derive_rank("LEY", "RESOLUCION 32 EXENTA NOMBRA REPRESENTANTE")
    assert rank == RESOLUCION and flagged is True
def test_clean_label_not_flagged():
    assert derive_rank("LEY", "LEY 20365 ESTABLECE…")[1] is False
```

- [ ] **Step 2: Run, expect fail** (`ModuleNotFoundError`). `./venv/bin/python -m pytest tests/extraction/test_norm_rank.py -q`

- [ ] **Step 3: Implement**

```python
# src/extraction/norm_rank.py
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
    # Title-driven rank (authoritative).
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
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(extraction): derive_rank — legal rank from title (DFL=ley, mislabel flag)`

---

## Task 2: `select_authoritative`

**Files:** Create `src/extraction/authority.py`; Test `tests/extraction/test_authority.py`

- [ ] **Step 1: Failing tests**

```python
from src.extraction.authority import select_authoritative

def C(norma, art, rank, fecha): return {"id_norma":norma,"articulo":art,"rank":rank,"fecha":fecha}

def test_higher_rank_beats_more_recent():
    # LEY 1183783 (no date) vs DECRETO 1160108 (2021): rank wins.
    r = select_authoritative([C("1183783","2",3,None), C("1160108","2",2,"2021-05-25")])
    assert r["status"]=="resolved" and r["id_norma"]=="1183783"
def test_same_rank_recent_wins():
    r = select_authoritative([C("1146553","5",2,"2019-02-01"), C("1160108","2",2,"2021-05-25")])
    assert r["status"]=="resolved" and r["id_norma"]=="1160108"
def test_tie_rank_and_date_is_conflict():
    r = select_authoritative([C("A","1",3,"2020-01-01"), C("B","2",3,"2020-01-01")])
    assert r["status"]=="conflict"
def test_single_candidate():
    r = select_authoritative([C("A","1",2,"2020-01-01")])
    assert r["status"]=="resolved" and r["id_norma"]=="A"
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement**

```python
# src/extraction/authority.py
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
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(extraction): select_authoritative — rank→date→conflict`

---

## Task 3: Runner `resolve_authority.py`

**Files:** Create `scripts/resolve_authority.py`

- [ ] **Step 1: Implement** (dry-run default; `--apply` writes `metadata.authoritative`/`authority_conflict`; idempotent via `metadata.authority_resolved`). For each concept with `define_termino` in >1 norma, build candidates `{id_norma, articulo, rank=derive_rank(n.tipo,n.titulo)[0], fecha=n.fecha_publicacion}`, call `select_authoritative`, write result. Follow `scripts/canonicalize_concepts.py` patterns (with_connection, dict_row, argparse, jsonb merge).

```python
# scripts/resolve_authority.py — skeleton (fill SQL like build_definitions_auto.py)
# SELECT c.id, a.id_norma, a.numero, n.tipo, n.titulo, n.fecha_publicacion
#   FROM conceptos c JOIN referencias r ON r.destino_concepto_id=c.id
#        AND r.tipo_relacion='define_termino'
#   JOIN articulos a ON a.id=r.origen_articulo_id JOIN normas n ON n.id_norma=a.id_norma
#  WHERE c.id IN (concepts with >1 distinct id_norma)
# group by concept → candidates → select_authoritative → UPDATE conceptos.metadata
```

- [ ] **Step 2: Dry-run**, verify the 28 multi-defined concepts get resolved/conflict; spot-check "Ministerio"→LEY 1183783.
- [ ] **Step 3: `--apply`**, verify idempotency (2nd run = 0 changes).
- [ ] **Step 4: Commit** `feat(extraction): resolve_authority ingestion runner`

---

## Task 4: Inject uses the authoritative pointer

**Files:** Modify `src/pipelines/concept_injection.py`; Test `tests/pipelines/test_concept_injection_authority.py`

- [ ] **Step 1: Failing test** — when `find_curated_definition`'s concept has `metadata.authoritative={norma,art}`, `inject_definition` injects THAT article (not the fecha-based one). (Monkeypatch the index lookup.)
- [ ] **Step 2-4:** Extend `_concept_index` to read `conceptos.metadata->'authoritative'`; when present, override the (id_norma, articulo) used. Conflict → leave fecha-based behaviour (B3 handles UX). Run tests.
- [ ] **Step 5: Commit** `feat(inject): prefer authoritative article when resolved`

---

## Task 5: Corregir el ground-truth del eval + medir

**Files:** Modify `scripts/build_eval_balanced.py` and/or `scripts/build_eval_diverse.py`; Modify handoff.

- [ ] **Step 1:** En el SQL que arma `expected_norma/articulo`, usar `metadata.authoritative` cuando exista (fallback a fecha). Regenerar `queries_diverse.jsonl`.
- [ ] **Step 2:** Re-correr el eval diverso (182q) y `score_diverse.py`. Esperado: `alias_sigla` cita_ok sube hacia ~100% (SEC/Comisión ahora esperan la Ley, que el sistema ya cita). Sin regresión en off_corpus.
- [ ] **Step 3:** Addendum en `docs/handoff-2026-05-20.md` con los números. Commit `feat(eval): authority-based ground-truth + re-measure`.

---

## Self-Review
- Spec §3 componentes → Tasks 1-5. ✓ · §5 incrementalidad → Task 3 (runner en ingesta). ✓ · §8 tests → Tasks 1,2,4. ✓ · §7 edges (sin fecha, flag, empate) → cubiertos en derive_rank/select_authoritative. ✓
- Sin placeholders salvo el SQL del runner (Task 3 marcado para completar siguiendo el patrón de build_definitions_auto.py — patrón referenciado, no inventado).
- Tipos consistentes: `derive_rank -> (int,bool)`, `select_authoritative(list[dict]) -> dict{status,...}` usados igual en runner y tests.
