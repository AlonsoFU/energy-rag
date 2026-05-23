# Desambiguación de nombres canónicos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraer de forma determinista el nombre canónico completo de cada concepto desde la apertura de su definición de glosario (regla A), degradando la palabra suelta a alias; alta confianza auto-aplica, lo dudoso va a una cola de revisión.

**Architecture:** Una función pura (`extract_canonical`) con la regla A + una función pura de decisión (`decide_action`) que añade idempotencia y detección de colisión, envueltas por un script de ingesta (`canonicalize_concepts.py`) que hace la I/O contra Postgres y escribe la cola YAML. El dry-run existente se refactoriza para importar la misma regla (DRY) y congela la distribución actual como test de regresión.

**Tech Stack:** Python 3.12, psycopg (Postgres), pytest, PyYAML. Spec: `docs/superpowers/specs/2026-05-22-canonical-concept-names-design.md`.

---

## File Structure

| archivo | responsabilidad |
|---|---|
| `src/extraction/canonical_names.py` (NUEVO) | Reglas puras: `extract_canonical`, `decide_action`, constantes de límite, `_na`. Sin DB. |
| `tests/extraction/test_canonical_names.py` (NUEVO) | Unit tests de las dos funciones puras + regresión de la distribución del corpus. |
| `scripts/canonicalize_concepts.py` (NUEVO) | Runner de ingesta: lee conceptos, decide, `--apply` (UPDATE) o cola; idempotente. |
| `scripts/dryrun_canonical_names.py` (MODIFICAR) | Refactor: importa `extract_canonical` del módulo (una sola fuente de verdad). |

Convenciones del repo a seguir (ya verificadas):
- DB: `from src.storage.connection import with_connection`; `conn.cursor(row_factory=dict_row)`; `conn.commit()`. Patrón `--dry-run`/`--apply` y `python -m scripts.X` como en `scripts/build_definitions_auto.py`.
- Cola de revisión: YAML bajo `glossary/incoming/` (ya existe `glossary/incoming/off_domain.yaml`).
- Tests con DB usan fixtures `postgres_container` (session) y `db_clean` de `tests/conftest.py`. Las dos funciones puras NO necesitan DB.

---

## Task 1: Regla A pura — `extract_canonical`

**Files:**
- Create: `src/extraction/canonical_names.py`
- Test: `tests/extraction/test_canonical_names.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/extraction/test_canonical_names.py
from src.extraction.canonical_names import extract_canonical


def test_no_fire_when_definition_does_not_restate_name():
    # "Cliente" is a genuine one-word term: its definition describes it.
    canonical, conf = extract_canonical(
        "Cliente", "Persona natural o jurídica que acredite dominio…")
    assert (canonical, conf) == (None, "no-fire")


def test_high_cut_at_period():
    canonical, conf = extract_canonical(
        "Comisión", "Comisión Nacional de Energía.")
    assert conf == "high"
    assert canonical == "Comisión Nacional de Energía"


def test_high_cut_at_participle():
    canonical, conf = extract_canonical(
        "Panel", "Panel de Expertos establecido en el Título VI del decreto…")
    assert conf == "high"
    assert canonical == "Panel de Expertos"


def test_high_preserves_original_case_and_accents():
    # The canonical span is verbatim, not lowercased/de-accented.
    canonical, conf = extract_canonical(
        "Coordinador",
        "Coordinador independiente del sistema eléctrico nacional, a quien…")
    assert conf == "high"
    assert canonical == "Coordinador independiente del sistema eléctrico nacional"


def test_low_when_too_long_cut_at_relative_clause():
    # Real "Comité": cuts at "a que se refiere" but is >8 extra words → review.
    canonical, conf = extract_canonical(
        "Comité",
        "Comité de adjudicación y supervisión del o los estudios de "
        "valorización a que se refiere el inciso segundo del artículo 108° de la Ley")
    assert conf == "low"
    assert canonical == ("Comité de adjudicación y supervisión del o los "
                         "estudios de valorización")


def test_no_fire_when_name_not_extended():
    # Definition starts with the name then a boundary → already canonical.
    canonical, conf = extract_canonical("Comité", "Comité. Algo más.")
    assert (canonical, conf) == (None, "no-fire")


def test_low_when_no_boundary_found():
    # Starts with name, extends, but no clean cut → review without proposal.
    canonical, conf = extract_canonical("Foo", "Foo bar baz qux quux corge")
    assert conf == "low"
    assert canonical is None


def test_empty_definition_is_no_fire():
    assert extract_canonical("X", "") == (None, "no-fire")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/extraction/test_canonical_names.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.extraction.canonical_names'`

- [ ] **Step 3: Write the module**

```python
# src/extraction/canonical_names.py
"""Deterministic canonical concept-name extraction (rule A).

When a glossary DEFINITION reopens by restating the concept name and
extending it into a longer noun phrase ("Comité: Comité de adjudicación y
supervisión…"), the real canonical name is that longer phrase and the bare
word is an alias. Legal-safe: the canonical name is a VERBATIM span of the
definition text (not invented, not re-accented); only orthographic
normalization is used to compare the prefix. No fuzzy, no thresholds beyond
the explicit word-count gate.

See spec docs/superpowers/specs/2026-05-22-canonical-concept-names-design.md.
"""
from __future__ import annotations

import re
import unicodedata

# Max words the canonical phrase may add over the bare name before it is
# considered too long to auto-apply (sent to review instead).
MAX_EXTRA_WORDS = 8

# Where the canonical noun phrase ends — cut BEFORE the first match.
BOUNDARY = re.compile(
    r"(?:[.;:,]"
    r"|\b(?:a\s+que|al\s+que|a\s+los\s+que|a\s+las\s+que|a\s+la\s+que"
    r"|que\s+se\s+refiere|que\s+establece|que\s+fija|que\s+indica"
    r"|que\s+se\s+\w+|en\s+adelante|seg[uú]n|conforme)\b"
    r"|\b(?:establecid[oa]s?|definid[oa]s?|constituid[oa]s?|conformad[oa]s?"
    r"|integrad[oa]s?|denominad[oa]s?|es|son|ser[aá]n?|consiste|corresponde"
    r"|comprende|contemplad[oa]s?|se\s+entender[aá])\b)",
    re.IGNORECASE,
)


def _na(s: str) -> str:
    """Lowercase + strip accents (orthographic normalization only)."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def extract_canonical(nombre: str, definicion: str) -> tuple[str | None, str]:
    """Return (canonical|None, confidence) where confidence is one of
    'high', 'low', 'no-fire'.

    - no-fire: definition does not restate+extend the name → leave concept.
    - high:    clean boundary, 1..MAX_EXTRA_WORDS added → auto-apply.
    - low:     boundary but too long, OR no clean cut → review queue.
    """
    if not definicion:
        return None, "no-fire"
    defi = definicion.strip()
    if not _na(defi).startswith(_na(nombre).strip()):
        return None, "no-fire"
    after = defi[len(nombre):]
    if not after[:1].isspace():            # must EXTEND with more words
        return None, "no-fire"
    m = BOUNDARY.search(after)
    if not m:
        return None, "low"                 # no clean cut → review, no proposal
    canonical = (nombre + after[: m.start()]).strip().rstrip(" ,;:.")
    extra_words = len(canonical.split()) - len(nombre.split())
    if extra_words <= 0:
        return None, "no-fire"             # boundary right after name
    conf = "high" if extra_words <= MAX_EXTRA_WORDS else "low"
    return canonical, conf
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/extraction/test_canonical_names.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add src/extraction/canonical_names.py tests/extraction/test_canonical_names.py
git commit -m "feat(extraction): rule A — deterministic canonical name from definition opening"
```

---

## Task 2: Decisión de ingesta pura — `decide_action`

**Files:**
- Modify: `src/extraction/canonical_names.py`
- Test: `tests/extraction/test_canonical_names.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/extraction/test_canonical_names.py
from src.extraction.canonical_names import decide_action


def test_decide_skip_when_already_canonicalized():
    a = decide_action("Comisión", "Comisión Nacional de Energía.",
                      metadata={"canonical_source": "definition_opening"},
                      other_names=set())
    assert a["action"] == "skip"
    assert a["reason"] == "already_canonicalized"


def test_decide_skip_on_no_fire():
    a = decide_action("Cliente", "Persona natural o jurídica…",
                      metadata=None, other_names=set())
    assert a["action"] == "skip"
    assert a["reason"] == "no-fire"


def test_decide_rename_on_high_no_collision():
    a = decide_action("Comisión", "Comisión Nacional de Energía.",
                      metadata=None, other_names=set())
    assert a["action"] == "rename"
    assert a["canonical"] == "Comisión Nacional de Energía"


def test_decide_review_on_low():
    a = decide_action(
        "Comité",
        "Comité de adjudicación y supervisión del o los estudios de "
        "valorización a que se refiere el inciso segundo…",
        metadata=None, other_names=set())
    assert a["action"] == "review"
    assert a["reason"].startswith("low_confidence")
    assert a["canonical"].startswith("Comité de adjudicación")


def test_decide_review_on_collision():
    # High-confidence canonical, but the canonical name already belongs to
    # ANOTHER concept → would be a merge, not a rename → review.
    from src.extraction.canonical_names import _na
    a = decide_action("Comisión", "Comisión Nacional de Energía.",
                      metadata=None,
                      other_names={_na("Comisión Nacional de Energía")})
    assert a["action"] == "review"
    assert a["reason"] == "collision"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./venv/bin/python -m pytest tests/extraction/test_canonical_names.py -q`
Expected: FAIL with `ImportError: cannot import name 'decide_action'`

- [ ] **Step 3: Add `decide_action` to the module**

```python
# append to src/extraction/canonical_names.py

def decide_action(nombre: str, definicion: str, metadata: dict | None,
                  other_names: set[str]) -> dict:
    """Decide what to do with one concept. Pure (no DB).

    `other_names` is the set of `_na`-normalized names of all OTHER concepts,
    used to detect a rename that would collide with an existing concept (a
    merge — routed to review, never auto-applied).

    Returns a dict with 'action' in {'skip','rename','review'} plus
    'canonical' and 'reason' where relevant.
    """
    if metadata and metadata.get("canonical_source"):
        return {"action": "skip", "reason": "already_canonicalized"}
    canonical, conf = extract_canonical(nombre, definicion)
    if conf == "no-fire":
        return {"action": "skip", "reason": "no-fire"}
    if conf == "low":
        return {"action": "review", "canonical": canonical,
                "reason": f"low_confidence: {'no_boundary' if canonical is None else 'too_long'}"}
    # high
    if _na(canonical) in other_names:
        return {"action": "review", "canonical": canonical, "reason": "collision"}
    return {"action": "rename", "canonical": canonical, "reason": "high"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./venv/bin/python -m pytest tests/extraction/test_canonical_names.py -q`
Expected: PASS (13 passed)

- [ ] **Step 5: Commit**

```bash
git add src/extraction/canonical_names.py tests/extraction/test_canonical_names.py
git commit -m "feat(extraction): decide_action — idempotency + collision routing"
```

---

## Task 3: Refactor del dry-run + test de regresión del corpus

**Files:**
- Modify: `scripts/dryrun_canonical_names.py`
- Test: `tests/extraction/test_canonical_names.py`

- [ ] **Step 1: Write the failing regression test**

Congela la distribución validada a mano (6 high, 1 low, 327 no-fire) sobre el corpus actual. Usa la DB de sesión.

```python
# append to tests/extraction/test_canonical_names.py
import pytest


@pytest.mark.usefixtures("postgres_container")
def test_corpus_distribution_frozen():
    """Regression: rule A over the current 334 concepts must keep the
    hand-validated distribution. If extraction or corpus changes, this fails
    on purpose so we re-validate."""
    from collections import Counter
    from src.storage.connection import with_connection
    from src.extraction.canonical_names import extract_canonical
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre, definicion FROM conceptos")
        rows = cur.fetchall()
    buckets = Counter(extract_canonical(n, d)[1] for n, d in rows)
    assert buckets["high"] == 6
    assert buckets["low"] == 1
    assert buckets["no-fire"] == 327
```

- [ ] **Step 2: Run test to verify it passes already**

Run: `./venv/bin/python -m pytest tests/extraction/test_canonical_names.py::test_corpus_distribution_frozen -q`
Expected: PASS (the module reproduces the dry-run's validated numbers). If it FAILS, the regex in Task 1 diverged from the validated dry-run — fix the regex to match `scripts/dryrun_canonical_names.py` before continuing.

- [ ] **Step 3: Refactor the dry-run to import from the module (DRY)**

Replace the inlined `extract_canonical`/`_BOUNDARY`/`_na` in `scripts/dryrun_canonical_names.py` with an import, keeping the reporting intact:

```python
# scripts/dryrun_canonical_names.py — replace the rule definitions with:
from src.extraction.canonical_names import extract_canonical, _na
# (delete the local _na, _BOUNDARY and extract_canonical defined here)
```

Leave `main()` and its printing unchanged; it already calls `extract_canonical(n, d)`.

- [ ] **Step 4: Run the dry-run to confirm identical output**

Run: `PYTHONPATH=. ./venv/bin/python scripts/dryrun_canonical_names.py`
Expected: `high: 6 / low: 1 / no-fire: 327 / colisiones: 0` (same as before refactor).

- [ ] **Step 5: Commit**

```bash
git add scripts/dryrun_canonical_names.py tests/extraction/test_canonical_names.py
git commit -m "refactor(extraction): dry-run imports rule A; freeze corpus distribution test"
```

---

## Task 4: Runner de ingesta `canonicalize_concepts.py`

**Files:**
- Create: `scripts/canonicalize_concepts.py`

- [ ] **Step 1: Write the runner**

```python
# scripts/canonicalize_concepts.py
"""Apply canonical-name extraction (rule A) over the concepts table.

Default is DRY-RUN (prints what it would do). With --apply it writes:
  - high confidence  → UPDATE conceptos (nombre=canónico, aliases += bare word,
                       metadata.canonical_source provenance). Idempotent.
  - low / collision  → glossary/incoming/canonical_review.yaml (human review).

Runs after build_definitions_auto.py in the ingestion flow. Idempotent: a
concept with metadata.canonical_source is skipped.

Run:  PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py
      PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py --apply
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml
from psycopg.rows import dict_row

from src.extraction.canonical_names import _na, decide_action
from src.storage.connection import with_connection

REVIEW_PATH = Path("glossary/incoming/canonical_review.yaml")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write changes to DB + review file (default: dry-run)")
    args = ap.parse_args()

    renames: list[dict] = []
    reviews: list[dict] = []

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, nombre, definicion, aliases, metadata "
                    "FROM conceptos ORDER BY nombre")
        rows = cur.fetchall()
        all_names = {_na(r["nombre"]) for r in rows}

        for r in rows:
            other = all_names - {_na(r["nombre"])}
            act = decide_action(r["nombre"], r["definicion"] or "",
                                r["metadata"], other)
            if act["action"] == "skip":
                continue
            if act["action"] == "review":
                reviews.append({
                    "concepto_id": r["id"],
                    "original_nombre": r["nombre"],
                    "canonical_propuesto": act.get("canonical"),
                    "motivo": act["reason"],
                    "definicion_inicio": (r["definicion"] or "")[:120],
                })
                continue
            # rename (high, no collision)
            renames.append({"id": r["id"], "bare": r["nombre"],
                            "canonical": act["canonical"]})

        print(f"renames (high): {len(renames)} | reviews: {len(reviews)}")
        for x in renames:
            print(f"  '{x['bare']}' → '{x['canonical']}'")

        if not args.apply:
            print("\n--dry-run: nothing written. Use --apply.")
            return

        for x in renames:
            cur.execute(
                """
                UPDATE conceptos
                   SET nombre = %(canonical)s,
                       aliases = (SELECT array_agg(DISTINCT a)
                                    FROM unnest(coalesce(aliases,'{}') || %(bare)s::text) a),
                       metadata = coalesce(metadata,'{}'::jsonb) || %(meta)s::jsonb
                 WHERE id = %(id)s
                """,
                {"canonical": x["canonical"], "bare": x["bare"], "id": x["id"],
                 "meta": json.dumps({
                     "canonical_source": "definition_opening",
                     "original_nombre": x["bare"],
                     "canonical_span": x["canonical"],
                     "confianza": 1.0,
                     "metodo": "regex_def_opening"})},
            )
        conn.commit()
        print(f"\nApplied {len(renames)} renames.")

    if args.apply:
        REVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
        REVIEW_PATH.write_text(
            yaml.safe_dump(reviews, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        print(f"Wrote {len(reviews)} review candidates → {REVIEW_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the dry-run**

Run: `PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py`
Expected: `renames (high): 6 | reviews: 1` and the 6 rename lines (Comisión, Coordinador, Informe Técnico de Valorización, Panel, Registro de Participación, Superintendencia). Nothing written.

- [ ] **Step 3: Verify idempotency precondition (read-only)**

Run: `docker exec energy_rag_pg psql -U energy_rag -d energy_rag -tA -c "SELECT count(*) FROM conceptos WHERE metadata ? 'canonical_source';"`
Expected: `0` (nothing canonicalized yet).

- [ ] **Step 4: Commit**

```bash
git add scripts/canonicalize_concepts.py
git commit -m "feat(extraction): canonicalize_concepts ingestion runner (dry-run/apply)"
```

---

## Task 5: Aplicar, verificar idempotencia y medir

**Files:**
- Modify: `docs/handoff-2026-05-20.md` (addendum con resultados)

- [ ] **Step 1: Apply to the DB**

Run: `PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py --apply`
Expected: `Applied 6 renames.` and `Wrote 1 review candidates → glossary/incoming/canonical_review.yaml`.

- [ ] **Step 2: Verify the renames + provenance**

Run:
```bash
docker exec energy_rag_pg psql -U energy_rag -d energy_rag -tA -c \
"SELECT nombre, aliases, metadata->>'original_nombre' FROM conceptos WHERE metadata ? 'canonical_source' ORDER BY nombre;"
```
Expected: 6 rows; e.g. `Comisión Nacional de Energía | {Comisión} | Comisión`.

- [ ] **Step 3: Verify idempotency (second run is a no-op)**

Run: `PYTHONPATH=. ./venv/bin/python scripts/canonicalize_concepts.py --apply`
Expected: `renames (high): 0 | reviews: 0` (all 6 now carry canonical_source → skipped).

- [ ] **Step 4: Re-measure citation correctness (honest, expected small)**

The injection alias index is cached in-process, so a fresh eval run picks up the renamed concepts (aliases now include the bare word). Re-run the focused A/B subset and re-score:
```bash
PYTHONPATH=. ./venv/bin/python -m src eval --eval-file data/eval/queries_ab_focused.jsonl --top-k 10 --save
# then, with the new results file <ts>:
PYTHONPATH=. ./venv/bin/python scripts/score_correctness.py --results data/eval/results/<ts>.json
```
Expected: off_corpus refusal stays 100%; cited_expected change is small (the spec states the citation lift lives in the deferred authority/conflict iteration). Record the actual numbers.

- [ ] **Step 5: Document + commit**

Add an addendum to `docs/handoff-2026-05-20.md` recording: 6 renames applied, the review-queue entry (Comité), idempotency confirmed, and the measured citation delta. Then:
```bash
git add docs/handoff-2026-05-20.md glossary/incoming/canonical_review.yaml
git commit -m "feat(extraction): apply canonical names (6 renames, 1 review) + measure"
```

---

## Self-Review

**1. Spec coverage** (against `2026-05-22-canonical-concept-names-design.md`):
- §3 algoritmo A (no-fire / fire / confianza / idempotencia) → Task 1 (`extract_canonical`) + Task 2 (`decide_action` idempotencia/colisión). ✓
- §4 componentes (módulo puro, runner, dry-run refactor, tests) → Tasks 1–4. ✓
- §5 cambios DB (UPDATE nombre/aliases/metadata) → Task 4 runner + Task 5 apply. ✓
- §6 cola de revisión YAML en `glossary/incoming/` → Task 4. ✓
- §7 integración post `build_definitions_auto` → documentado en docstring del runner (Task 4) + handoff (Task 5). ✓
- §8 medición/aceptación (distribución congelada + re-medir, off_corpus 100%) → Task 3 (regresión) + Task 5 (medición). ✓
- §9 legal-safety (verbatim, sin fuzzy, alta confianza acotada, review) → garantizado por Task 1 (span verbatim, MAX_EXTRA_WORDS) + Task 2 (review). ✓
- §10/§11 diferido/YAGNI (autoridad, ambigüedad, focused gating, siglas, aplicar la cola) → fuera de alcance por diseño; ningún task los toca. ✓

**2. Placeholder scan:** sin TBD/TODO; todo código y comandos concretos. ✓

**3. Type consistency:** `extract_canonical -> (str|None, str)` usado igual en Task 2/3/4; `decide_action(nombre, definicion, metadata, other_names) -> dict` con claves `action/canonical/reason` consistentes entre test y runner; `_na` importado donde se usa. ✓

**Nota:** si Task 3 Step 2 falla, la regex de Task 1 difiere del dry-run validado — alinear antes de seguir (la distribución 6/1/327 es la verdad de referencia).
