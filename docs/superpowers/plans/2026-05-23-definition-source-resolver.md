# Resolutor de fuente autoritativa de definiciones — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use `- [ ]`.

**Goal:** Para cada concepto cuya definición marcada es floja, elegir la fuente correcta: determinista cuando hay seguridad (alta confianza, se aplica), tentativa por LLM cuando la regla no alcanza (baja confianza, se aplica con bandera `needs_review`). Todo auditable.

**Architecture:** Tres capas puras + un runner. Capa 0 `definition_quality` detecta definiciones flojas (etiqueta/corta/remisión). Capa 1 `definition_source` resuelve por sustancia→jerarquía→fecha (reusa `derive_rank`/`select_authoritative` de B1). Capa 2 `definition_proposer` llama al LLM local sólo para el residuo y devuelve una decisión tentativa. El runner `resolve_definition_sources.py` orquesta, escribe el puntero `conceptos.metadata.definition_source` (con `needs_review` si baja confianza) + un YAML de auditoría, idempotente. El inject prefiere ese puntero.

**Tech Stack:** Python 3.12, psycopg (dict_row), pytest, Ollama vía `get_llm_provider()`. Construye sobre la rama `feat/authority-resolution` (B1).

**Spec:** `docs/superpowers/specs/2026-05-23-definition-source-resolver-design.md`

---

## File Structure

- `src/extraction/definition_quality.py` (NUEVO, puro) — Capa 0: detección de definición floja.
- `src/extraction/definition_source.py` (NUEVO, puro) — Capa 1: resolución determinista entre candidatos.
- `src/extraction/definition_proposer.py` (NUEVO) — Capa 2: decisión tentativa vía LLM (inyectable para test).
- `scripts/resolve_definition_sources.py` (NUEVO) — runner: orquesta 0→2, escribe puntero+bandera+YAML.
- `src/pipelines/concept_injection.py` (MODIFICAR) — el inject prefiere `metadata.definition_source`.
- Tests espejo en `tests/extraction/` y `tests/pipelines/`.

Convención de candidato (un dict por artículo que define el concepto):
`{"id_norma": str, "articulo": str, "rank": int, "fecha": str|None, "definicion": str}`.

---

## Task 1: Capa 0 — detección de definición floja

**Files:**
- Create: `src/extraction/definition_quality.py`
- Test: `tests/extraction/test_definition_quality.py`

- [ ] **Step 1: Write the failing test**

```python
from src.extraction.definition_quality import (
    is_label, is_remission, suspect_definition,
)


def test_circular_label_is_suspect():
    # Definition only restates the concept name → label.
    sus, reasons = suspect_definition(
        "Superintendencia de Electricidad y Combustibles",
        "la Superintendencia de Electricidad y Combustibles.")
    assert sus is True and "label" in reasons


def test_remission_is_suspect():
    sus, reasons = suspect_definition(
        "Coordinador", "el Coordinador a que se refiere el artículo 212 de la ley.")
    assert sus is True and "remission" in reasons


def test_substantive_definition_not_suspect():
    sus, reasons = suspect_definition(
        "Comisión Nacional de Energía",
        "persona jurídica de derecho público, funcionalmente descentralizada, "
        "con patrimonio propio y plena capacidad para adquirir y ejercer derechos.")
    assert sus is False and reasons == []


def test_is_label_true_when_only_name_words():
    assert is_label("Panel de Expertos", "el Panel de Expertos") is True


def test_is_label_false_when_adds_content():
    assert is_label("Panel de Expertos",
                    "órgano que resuelve discrepancias entre empresas eléctricas") is False


def test_is_remission_detects_cross_reference():
    assert is_remission("lo señalado en el artículo 5 del presente reglamento") is True
    assert is_remission("órgano técnico autónomo") is False


def test_empty_definition_is_suspect():
    sus, reasons = suspect_definition("X", "")
    assert sus is True and "empty" in reasons
```

- [ ] **Step 2: Run, expect fail** — `PYTHONPATH=. ./venv/bin/python -m pytest tests/extraction/test_definition_quality.py -q` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/extraction/definition_quality.py
"""Capa 0 — detect a WEAK marked definition (route it to the resolver).

These are cheap, topic-neutral SUSPICION signals; they only decide what to
look at, never the legal answer. A definition is suspect when it is empty, a
circular label (it mostly restates the concept's own name), too short to carry
substance, or a remission (it points elsewhere instead of defining).
"""
from __future__ import annotations

import re
import unicodedata

# A definition that, after removing the concept's own words, has at least this
# many remaining content words is considered substantive.
_MIN_CONTENT_WORDS = 4
_STOP = {"el", "la", "los", "las", "un", "una", "de", "del", "y", "o", "a",
         "que", "se", "en", "al", "lo", "su", "sus", "para", "por", "con"}
_REMISSION = re.compile(
    r"\b(a que se refiere|se refiere|señalad[oa] en|definid[oa] en|"
    r"establecid[oa] en|en los t[ée]rminos de|conforme a lo dispuesto)\b",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def _content_words(text: str) -> list[str]:
    words = re.findall(r"[a-záéíóúñ]{2,}", _norm(text))
    return [w for w in words if w not in _STOP]


def is_label(nombre: str, definicion: str) -> bool:
    """True if the definition's content words are essentially just the name's."""
    name_words = set(_content_words(nombre))
    extra = [w for w in _content_words(definicion) if w not in name_words]
    return len(extra) < _MIN_CONTENT_WORDS


def is_remission(definicion: str) -> bool:
    return bool(_REMISSION.search(definicion or ""))


def suspect_definition(nombre: str, definicion: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not (definicion or "").strip():
        reasons.append("empty")
        return True, reasons
    if is_remission(definicion):
        reasons.append("remission")
    if is_label(nombre, definicion):
        reasons.append("label")
    return (len(reasons) > 0, reasons)
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(extraction): definition_quality — detect weak/label/remission definitions`

---

## Task 2: Capa 1 — resolución determinista entre candidatos

**Files:**
- Create: `src/extraction/definition_source.py`
- Test: `tests/extraction/test_definition_source.py`

- [ ] **Step 1: Write the failing test**

```python
from src.extraction.definition_source import resolve_definition_source

NAME = "Coordinador"

def C(norma, art, rank, fecha, definicion):
    return {"id_norma": norma, "articulo": art, "rank": rank,
            "fecha": fecha, "definicion": definicion}

LABEL = "el Coordinador"
SUBSTANCE = ("órgano técnico independiente encargado de la coordinación de la "
             "operación del sistema eléctrico nacional, con patrimonio propio.")

def test_substantive_beats_label_same_rank():
    r = resolve_definition_source(NAME, [
        C("A", "2", 2, "2019-01-01", LABEL),
        C("B", "5", 2, "2018-01-01", SUBSTANCE),
    ])
    assert r["status"] == "resolved" and r["id_norma"] == "B"
    assert r["confianza"] == "alta" and r["criterio"] == "sustancia"

def test_higher_rank_substantive_wins():
    # LEY (rank 3) that is ALSO the most recent beats the older DECRETO: rank and
    # recency AGREE → safe to resolve by hierarchy. A higher-rank-but-OLDER norm
    # is instead unresolved (see test_rank_disagrees_with_recency_is_unresolved) —
    # rank must not auto-win over a more-recent norm of possibly different context.
    r = resolve_definition_source(NAME, [
        C("A", "2", 2, "2020-01-01", SUBSTANCE),
        C("B", "5", 3, "2021-01-01", SUBSTANCE + " Ley."),
    ])
    assert r["status"] == "resolved" and r["id_norma"] == "B"
    assert r["criterio"] == "jerarquia"

def test_rank_disagrees_with_recency_is_unresolved():
    # Substantive LEY (no date) vs substantive DECRETO (recent): B1 rule → ask.
    r = resolve_definition_source(NAME, [
        C("A", "2", 3, None, SUBSTANCE),
        C("B", "5", 2, "2021-01-01", SUBSTANCE),
    ])
    assert r["status"] == "unresolved"

def test_only_labels_is_unresolved():
    r = resolve_definition_source(NAME, [
        C("A", "2", 2, "2019-01-01", LABEL),
        C("B", "5", 2, "2018-01-01", "el Coordinador."),
    ])
    assert r["status"] == "unresolved" and r["reason"] == "no-substantive-candidate"

def test_single_substantive_resolves():
    r = resolve_definition_source(NAME, [C("A", "2", 2, "2019-01-01", SUBSTANCE)])
    assert r["status"] == "resolved" and r["id_norma"] == "A"
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement**

```python
# src/extraction/definition_source.py
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
    subs = _substantive(nombre, candidates)
    if not subs:
        return {"status": "unresolved", "reason": "no-substantive-candidate"}
    if len(subs) == 1:
        w = subs[0]
        return {"status": "resolved", "id_norma": w["id_norma"],
                "articulo": w["articulo"], "confianza": "alta",
                "criterio": "sustancia"}
    # >1 substantive: defer the rank/date/context decision to B1's resolver.
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
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(extraction): definition_source — deterministic substance→rank→date resolution`

---

## Task 3: Capa 2 — decisión tentativa vía LLM

**Files:**
- Create: `src/extraction/definition_proposer.py`
- Test: `tests/extraction/test_definition_proposer.py`

- [ ] **Step 1: Write the failing test** (LLM inyectado, sin red)

```python
from src.components.llm import MockLLMProvider
from src.extraction.definition_proposer import propose_definition_source


def test_proposer_returns_low_confidence_pick():
    # MockLLMProvider matches canned_responses by SUBSTRING of the prompt;
    # "Concepto" appears in every proposer prompt → use it as the key.
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "B", "articulo": "23", '
                    '"criterio": "especialidad", '
                    '"fundamento": "ley orgánica del organismo"}'
    })
    cands = [
        {"id_norma": "A", "articulo": "2", "rank": 3, "fecha": None,
         "definicion": "la SEC."},
        {"id_norma": "B", "articulo": "23", "rank": 3, "fecha": "1985-05-22",
         "definicion": "entidad que sucedió legalmente al Servicio…"},
    ]
    r = propose_definition_source("SEC", cands, llm=llm)
    assert r["id_norma"] == "B" and r["articulo"] == "23"
    assert r["confianza"] == "baja"
    assert r["criterio"] == "especialidad"
    assert r["fundamento"]


def test_proposer_failopen_on_bad_json():
    llm = MockLLMProvider(canned_responses={"Concepto": "no soy json"})
    r = propose_definition_source("SEC", [
        {"id_norma": "A", "articulo": "2", "rank": 3, "fecha": None,
         "definicion": "la SEC."}], llm=llm)
    assert r["status"] == "no-proposal"


def test_proposer_rejects_pick_outside_candidates():
    llm = MockLLMProvider(canned_responses={
        "Concepto": '{"id_norma": "Z", "articulo": "9", "criterio": "x", '
                    '"fundamento": "y"}'})
    r = propose_definition_source("SEC", [
        {"id_norma": "A", "articulo": "2", "rank": 3, "fecha": None,
         "definicion": "la SEC."}], llm=llm)
    assert r["status"] == "no-proposal"
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** (verify `MockLLMProvider` echoes `canned_responses["__default__"]`; if its key differs, adjust the test key — do not change behaviour)

```python
# src/extraction/definition_proposer.py
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
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(extraction): definition_proposer — tentative LLM pick (low confidence, fail-open)`

---

## Task 4: Runner `resolve_definition_sources.py`

**Files:**
- Create: `scripts/resolve_definition_sources.py`
- (Validación manual; sin test unitario — toca DB real, igual que `resolve_authority.py`.)

- [ ] **Step 1: Implement** (sigue el patrón EXACTO de `scripts/resolve_authority.py`: `with_connection`, `dict_row`, argparse `--apply`, jsonb merge, dry-run por defecto)

```python
# scripts/resolve_definition_sources.py
"""Resolve each concept's authoritative DEFINITION source (Capa 0→2).

For every concept, gather its defining articles as candidates; if the marked
definition is weak (Capa 0), try the deterministic resolver (Capa 1, high
confidence) and, failing that, the tentative LLM proposer (Capa 2, low
confidence). Writes conceptos.metadata.definition_source = {id_norma, articulo,
criterio, confianza, needs_review} — high confidence has needs_review=False,
low confidence True. Also writes an auditable YAML. Dry-run by default;
--apply writes. Idempotent (recomputes from current data each run).

Run:  PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py
      PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py --apply
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml
from psycopg.rows import dict_row

from src.extraction.definition_quality import suspect_definition
from src.extraction.definition_source import resolve_definition_source
from src.extraction.definition_proposer import propose_definition_source
from src.extraction.norm_rank import derive_rank
from src.storage.connection import with_connection

REVIEW_PATH = Path("glossary/incoming/definition_source_review.yaml")

SQL = """
SELECT c.id AS concepto_id, c.nombre, c.definicion,
       a.id_norma, a.numero AS articulo, a.texto,
       n.tipo, n.titulo, n.fecha_publicacion
FROM conceptos c
JOIN referencias r ON r.destino_concepto_id = c.id
                  AND r.tipo_relacion = 'define_termino'
JOIN articulos a ON a.id = r.origen_articulo_id
JOIN normas n ON n.id_norma = a.id_norma
ORDER BY c.id, a.id_norma, a.numero
"""


def build_candidates(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        rank, _ = derive_rank(r["tipo"], r["titulo"])
        out.append({
            "id_norma": r["id_norma"], "articulo": r["articulo"],
            "rank": rank,
            "fecha": r["fecha_publicacion"].isoformat() if r["fecha_publicacion"] else None,
            # Prefer the concept-level curated definition; fall back to article text.
            "definicion": (r["definicion"] or r["texto"] or "")[:2000],
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to DB + YAML (default dry-run)")
    args = ap.parse_args()

    decisions: list[dict] = []
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL)
        by_concept: dict[tuple, list[dict]] = defaultdict(list)
        meta: dict[tuple, dict] = {}
        for row in cur.fetchall():
            key = (row["concepto_id"], row["nombre"])
            by_concept[key].append(row)
            meta.setdefault(key, {"definicion": row["definicion"]})

        for (cid, nombre), rows in by_concept.items():
            definicion = meta[(cid, nombre)]["definicion"] or ""
            suspect, reasons = suspect_definition(nombre, definicion)
            if not suspect:
                continue  # current marked definition is fine
            cands = build_candidates(rows)
            res = resolve_definition_source(nombre, cands)
            if res["status"] == "resolved":
                d = {"id": cid, "nombre": nombre, "id_norma": res["id_norma"],
                     "articulo": res["articulo"], "criterio": res["criterio"],
                     "confianza": "alta", "needs_review": False,
                     "fundamento": "", "reasons": reasons}
            else:
                prop = propose_definition_source(nombre, cands)
                if prop.get("status") != "proposed":
                    d = {"id": cid, "nombre": nombre, "id_norma": None,
                         "articulo": None, "criterio": "ninguno",
                         "confianza": "baja", "needs_review": True,
                         "fundamento": "sin propuesta (regla no resolvió, LLM no propuso)",
                         "reasons": reasons}
                else:
                    d = {"id": cid, "nombre": nombre, "id_norma": prop["id_norma"],
                         "articulo": prop["articulo"], "criterio": prop["criterio"],
                         "confianza": "baja", "needs_review": True,
                         "fundamento": prop["fundamento"], "reasons": reasons}
            decisions.append(d)

        applied = [d for d in decisions if d["id_norma"]]
        review = [d for d in decisions if d["needs_review"]]
        print(f"suspect concepts: {len(decisions)} | applied-mark: {len(applied)} "
              f"| needs_review: {len(review)}")
        for d in decisions:
            tag = "✓ alta" if not d["needs_review"] else "⚠ baja/revisar"
            print(f"  {tag} {d['nombre'][:32]:32} → {d['id_norma']} art {d['articulo']} "
                  f"({d['criterio']}; {','.join(d['reasons'])})")

        if not args.apply:
            print("\n--dry-run: nada escrito. Usa --apply.")
            return

        for d in decisions:
            if not d["id_norma"]:
                continue
            cur.execute(
                "UPDATE conceptos SET metadata = coalesce(metadata,'{}'::jsonb) "
                "|| %(m)s::jsonb WHERE id = %(id)s",
                {"id": d["id"], "m": json.dumps({
                    "definition_source": {
                        "id_norma": d["id_norma"], "articulo": d["articulo"],
                        "criterio": d["criterio"], "confianza": d["confianza"],
                        "needs_review": d["needs_review"]},
                    "def_source_resolved": {"metodo": "capas_0_2"}})},
            )
        conn.commit()
        print(f"\nAplicado: {len(applied)} apuntadores ({len(review)} con needs_review).")

    REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_PATH.write_text(
        yaml.safe_dump(review, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Escrito {len(review)} pendientes → {REVIEW_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run.** `PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py`
  Esperado: SEC / Comisión / Ministerio aparecen como suspect; los institucionales caen en `⚠ baja/revisar` con candidato a ley orgánica (29819 / 1008692) y criterio `especialidad`.
- [ ] **Step 3: Commit** `feat(extraction): resolve_definition_sources runner (deterministic + tentative, audited)`

---

## Task 5: El inject prefiere `definition_source`

**Files:**
- Modify: `src/pipelines/concept_injection.py`
- Test: `tests/pipelines/test_concept_injection_defsource.py`

- [ ] **Step 1: Write the failing test**

```python
from src.pipelines import concept_injection as ci


def test_definition_source_pointer_present():
    md = {"definition_source": {"id_norma": "29819", "articulo": "23",
                                "confianza": "baja", "needs_review": True}}
    assert ci.definition_source_pointer(md) == ("29819", "23")


def test_definition_source_pointer_absent():
    assert ci.definition_source_pointer({}) is None
    assert ci.definition_source_pointer(None) is None


def test_definition_source_used_even_if_low_confidence(monkeypatch):
    # Low-confidence (needs_review) pointer is still used by inject.
    monkeypatch.setattr(ci, "_concept_index", lambda: {
        "sec": ("29819", "23", "entidad que sucedió legalmente…",
                "Superintendencia de Electricidad y Combustibles"),
    })
    out = ci.inject_definition("qué es SEC", [])
    assert out[0]["id_norma"] == "29819" and out[0]["articulo_numero"] == "23"
```

- [ ] **Step 2: Run, expect fail** (no `definition_source_pointer`).

- [ ] **Step 3: Implement** — add the helper near `authoritative_pointer` and have `_concept_index` prefer `definition_source` over `authoritative` over the fecha-based pick.

```python
# src/pipelines/concept_injection.py — add after authoritative_pointer(...)

def definition_source_pointer(metadata: Optional[dict]) -> Optional[tuple[str, str]]:
    """Return (id_norma, articulo) from metadata.definition_source if present.

    Used even when confianza is 'baja' (needs_review): the system uses the
    tentative source immediately; the flag is a curation marker, not a gate.
    More specific than authoritative_pointer — prefer it when both exist.
    """
    if not metadata:
        return None
    ds = metadata.get("definition_source")
    if not ds:
        return None
    norma, art = ds.get("id_norma"), ds.get("articulo")
    if norma is None or art is None:
        return None
    return (str(norma), str(art))
```

Then in BOTH SELECT loops of `_concept_index`, replace the pointer-selection line so `definition_source` wins:

```python
            # precedence: definition_source (this skill) > authoritative (B1) > fecha
            ptr = definition_source_pointer(metadata) or authoritative_pointer(metadata)
            norma_f, art_f = ptr if ptr else (str(id_norma), str(articulo))
            out[key] = (norma_f, art_f, definicion or "", nombre)  # name loop
```
(en el loop de aliases usar la variante con `_nombre` ya existente, misma precedencia).

- [ ] **Step 4: Run, expect pass.** Luego corre toda la suite: `PYTHONPATH=. ./venv/bin/python -m pytest tests/extraction tests/pipelines -q` (esperado: pasa todo salvo el stale conocido `test_generate_passes_response_format`).
- [ ] **Step 5: Commit** `feat(inject): prefer definition_source pointer (incl. low-confidence) over authoritative`

---

## Task 6: Correrlo sobre los datos + verificar + medir

**Files:** ninguno (operación).

- [ ] **Step 1:** Asegura DB+Ollama arriba: `docker start energy_rag_pg`; `curl -sf http://localhost:11434/api/tags >/dev/null && echo ok`.
- [ ] **Step 2:** Dry-run y revisa la lista: `PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py`. Confirma que SEC/Comisión/Ministerio salen `⚠ baja/revisar` apuntando a ley orgánica.
- [ ] **Step 3:** Aplica: `PYTHONPATH=. ./venv/bin/python scripts/resolve_definition_sources.py --apply`. Revisa `glossary/incoming/definition_source_review.yaml`.
- [ ] **Step 4:** Verifica en vivo: `PYTHONPATH=. ./venv/bin/python -m src ask "qué es SEC" -k 10` → debe citar `[Art. 23 de 29819]` (ley orgánica) y la respuesta describir la SEC, no la etiqueta.
- [ ] **Step 5:** Idempotencia: 2ª corrida `--apply` no cambia los de alta confianza ni re-marca lo ya resuelto.
- [ ] **Step 6:** Medición del SKILL (no del eval): contar en el YAML cuántos `needs_review` y, tras tu revisión manual, cuántos confirmaste correctos = tasa de acierto de la capa tentativa. Anota el número en el handoff.
- [ ] **Step 7: Commit** del YAML de revisión: `chore(glossary): definition_source review queue (needs_review)`.

---

## Self-Review

- **Cobertura del spec:** §5 Capa 0 → Task 1 ✓ · §6 Capa 1 → Task 2 ✓ · §7 Capa 2 → Task 3 ✓ · §8 confianza/registro (puntero + YAML + needs_review) → Task 4 ✓ · §9 inject → Task 5 ✓ · §11 correr en cadena + §14 integración → Task 6 ✓ · §12 legal-safety (alta sin bandera / baja con needs_review, fail-open) → Tasks 3,4 ✓.
- **Especialidad (§10):** hoy la Capa 1 no infiere ámbito (no hay dato); por eso esos casos caen a Capa 2 (proposer) que sí puede argumentar especialidad — coherente con el spec. No se inventa ámbito en código determinista. ✓
- **Derogación (decisión usuario, opción A):** fuera de alcance (B2); el runner no la chequea hoy → los casos sin vigencia verificada caen en `needs_review`. Sin tarea aquí, por diseño.
- **Placeholders:** ninguno; todo el código está completo.
- **Consistencia de tipos:** candidato `{id_norma,articulo,rank,fecha,definicion}` usado igual en Tasks 2,3,4. `resolve_definition_source(nombre, candidates)->{status,...}` y `propose_definition_source(nombre,candidates,llm=)->{status,...}` consistentes con el runner. `definition_source_pointer` espeja a `authoritative_pointer` (B1). ✓
- **MockLLMProvider (verificado):** matchea `canned_responses` por **substring del prompt**; los tests de Task 3 usan la clave `"Concepto"` (aparece en todo prompt del proposer). `.generate(...).text` y la firma están confirmados contra `src/components/llm.py`.
