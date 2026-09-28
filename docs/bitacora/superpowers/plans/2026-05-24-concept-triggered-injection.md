# Inyección disparada por concepto (no por fraseo) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** Que la inyección del artículo definidor se dispare **detectando el concepto** que centra la pregunta (general, cualquier fraseo) en vez de una lista de aperturas hardcodeadas ("qué es X"). Ataca los fallos de `fraseo_variado` (la inyección no se activaba en otros fraseos → el LLM citaba el artículo hermano equivocado).

**Architecture:** Reusar `extract_query_concepts(query, conceptos)` (ya existe, match exacto normalizado de nombres/aliases — phrasing-agnóstico, no fuzzy). Nuevo `find_subject_concept(query)`: si la query menciona **exactamente un** concepto curado con artículo definidor → ese es el sujeto → se inyecta su artículo (alias-aware si se mencionó por alias). 0 ó >1 conceptos → no se fuerza (relacional/ambiguo). Determinista en el disparo (match exacto contra datos curados) y en la respuesta (artículo curado).

**Tech Stack:** Python 3.12, pytest. Sobre rama `feat/definition-source-resolver`.

**Principio:** difuso/semántico solo para *entender* (qué concepto); exacto para *responder* (artículo curado). Sin lista de fraseos.

---

## Task 1: `find_subject_concept` (gatillo por concepto)

**Files:** Modify `src/pipelines/concept_injection.py`; Test `tests/pipelines/test_concept_injection_subject.py`

- [ ] **Step 1: Failing test**

```python
from src.pipelines import concept_injection as ci


def _index():
    # normalized-key -> (id_norma, articulo, definicion, canonical)
    return {
        "coordinador independiente del sistema electrico nacional":
            ("1160108", "2", "órgano técnico independiente…",
             "Coordinador independiente del sistema eléctrico nacional"),
        "cen": ("1160108", "2", "órgano técnico independiente…",
                "Coordinador independiente del sistema eléctrico nacional"),
    }


def _concepts():
    return [{"nombre": "Coordinador independiente del sistema eléctrico nacional",
             "aliases": ["CEN"]},
            {"nombre": "Panel de Expertos", "aliases": []}]


def test_subject_found_any_phrasing(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    for q in ["explícame qué es el Coordinador independiente del sistema eléctrico nacional",
              "a qué se refiere el Coordinador independiente del sistema eléctrico nacional",
              "Coordinador independiente del sistema eléctrico nacional"]:
        s = ci.find_subject_concept(q)
        assert s is not None and s[0] == "1160108" and s[1] == "2"


def test_alias_subject_sets_alias_token(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    s = ci.find_subject_concept("qué dice la norma sobre el CEN")
    # tuple: (id_norma, articulo, definicion, canonical, alias_or_None)
    assert s is not None and s[4] == "CEN"


def test_no_concept_returns_none(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    assert ci.find_subject_concept("cuál es la capital de Australia") is None


def test_two_distinct_concepts_returns_none(monkeypatch):
    # relational query mentioning two DISTINCT (non-overlapping) concepts → don't force.
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    s = ci.find_subject_concept(
        "relación entre el Coordinador independiente del sistema eléctrico nacional y el Panel de Expertos")
    assert s is None


def test_overlapping_match_picks_longest(monkeypatch):
    # "Coordinador" is a substring of the long name → SAME subject, not two.
    # Must resolve to ONE subject (the longest), not None.
    idx = {"coordinador": ("999", "1", "x", "Coordinador"),
           "coordinador independiente del sistema electrico nacional":
               ("1160108", "2", "órgano técnico…",
                "Coordinador independiente del sistema eléctrico nacional")}
    monkeypatch.setattr(ci, "_concept_index", lambda: idx)
    monkeypatch.setattr(ci, "_all_concepts", lambda: [
        {"nombre": "Coordinador", "aliases": []},
        {"nombre": "Coordinador independiente del sistema eléctrico nacional", "aliases": ["CEN"]}])
    s = ci.find_subject_concept("qué es el Coordinador independiente del sistema eléctrico nacional")
    assert s is not None and s[0] == "1160108"  # the longest/most-specific won
```

- [ ] **Step 2: Run, expect fail** (`find_subject_concept` / `_all_concepts` missing).

- [ ] **Step 3: Implement** — add to `concept_injection.py`:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def _all_concepts() -> list[dict]:
    """[{nombre, aliases}] for every concept (for phrasing-agnostic detection)."""
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre, aliases FROM conceptos")
        return [{"nombre": n, "aliases": a or []} for n, a in cur.fetchall()]


def _matched_term(query_norm: str, c: dict):
    """Return the literal term (canonical or alias) by which concept c matched
    the query, plus whether it was an alias; or (None, False)."""
    from src.pipelines.retrieve import find_term_in_query
    if find_term_in_query(c["nombre"], query_norm):
        return c["nombre"], False
    for a in (c["aliases"] or []):
        if a and find_term_in_query(a, query_norm):
            return a, True
    return None, False


def find_subject_concept(query: str):
    """Return (id_norma, articulo, definicion, canonical, alias_or_None) when the
    query centers on a SINGLE curated concept that has a defining article; else
    None. Phrasing-agnostic: detects the concept by exact normalized match of
    curated names/aliases (no opener regex, no fuzzy).

    Over-matching guard: a long concept name often contains shorter concept
    names as substrings ("Coordinador" ⊂ "Coordinador independiente…"). We keep
    the LONGEST matched term and drop any other whose matched term is contained
    in it (same subject at different granularity). If a DISTINCT (non-contained)
    concept also matched → relational/ambiguous → None.
    """
    nq = normalize_for_match(query)
    matched = []  # (canonical, term, is_alias)
    for c in _all_concepts():
        term, is_alias = _matched_term(nq, c)
        if term:
            matched.append((c["nombre"], term, is_alias))
    if not matched:
        return None
    matched.sort(key=lambda m: len(m[1]), reverse=True)
    subject = matched[0]
    subj_term_n = normalize_for_match(subject[1])
    # Any other match whose term is NOT contained in the subject's term = distinct.
    for canon, term, _ in matched[1:]:
        if normalize_for_match(term) not in subj_term_n:
            return None  # ≥2 distinct concepts → relational
    entry = _concept_index().get(normalize_for_match(subject[0]))
    if entry is None:
        return None
    id_norma, articulo, definicion, canon = entry
    return (id_norma, articulo, definicion, canon, subject[1] if subject[2] else None)
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(inject): find_subject_concept — phrasing-agnostic concept trigger`

---

## Task 2: inject usa el gatillo por concepto

**Files:** Modify `src/pipelines/concept_injection.py`; Test `tests/pipelines/test_concept_injection_subject.py` (add)

- [ ] **Step 1: Failing test** (add)

```python
def test_inject_fires_on_nonopener_phrasing(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    out = ci.inject_definition(
        "explícame qué es el Coordinador independiente del sistema eléctrico nacional", [])
    assert out and out[0].get("_injected") is True
    assert out[0]["id_norma"] == "1160108" and out[0]["articulo_numero"] == "2"


def test_inject_alias_nonopener(monkeypatch):
    monkeypatch.setattr(ci, "_concept_index", _index)
    monkeypatch.setattr(ci, "_all_concepts", _concepts)
    out = ci.inject_definition("información sobre el CEN", [])
    assert out and out[0].get("_alias_link") is True  # alias-aware doc
```

- [ ] **Step 2: Run, expect fail.**

- [ ] **Step 3: Implement** — in `inject_definition`, replace the opener-based trigger so it uses `find_subject_concept` as the general path. Concretely, change the head of `inject_definition`:

```python
def inject_definition(query: str, docs: list[dict]) -> list[dict]:
    subject = find_subject_concept(query)
    if subject is None:
        return docs
    id_norma, articulo, definicion, canonical, alias = subject
    is_alias = alias is not None
    if is_alias and definicion.strip():
        rest = [d for d in docs if not (str(d.get("id_norma")) == id_norma
                and str(d.get("articulo_numero")) == articulo)]
        return [_alias_link_doc(alias.strip(), canonical, definicion, id_norma, articulo)] + rest
    # ... keep the existing focused / legacy (move-to-front or fetch) branch below,
    # using id_norma/articulo/definicion as before (drop the old extract_definitional_term
    # and find_curated_definition calls).
```
Keep `_alias_link_doc`, `_focused_doc`, `fetch_article_doc`, and the focused/legacy tail unchanged. Remove now-unused `extract_definitional_term`/`find_curated_definition` ONLY if nothing else imports them (grep first; if referenced elsewhere/tests, leave them defined but unused by inject).

- [ ] **Step 4: Run** the new file + full suite: `PYTHONPATH=. ./venv/bin/python -m pytest tests/pipelines tests/extraction -q`. Expected: pass except the known stale `test_generate_passes_response_format`. If `test_concept_injection_alias.py` / `_defsource.py` / `_authority.py` break because they relied on the opener path, update them to the concept trigger (same behaviour, just triggered via a concept-bearing query) — do NOT weaken assertions about WHICH article is injected.
- [ ] **Step 5: Commit** `feat(inject): trigger injection by detected subject concept (drop opener regex)`

---

## Task 3 (controller runs, GPU): regenerar gold + re-eval

- [ ] Regenerar gold del set diverso usando `definition_source`/autoridad confirmada donde exista (que el gold deje de penalizar las citas a la ley orgánica). Script: extender `build_eval_diverse.py` para preferir `metadata.definition_source` → `authoritative` → fecha.
- [ ] Re-eval `queries_diverse.jsonl` (188q) con DB+GPU exclusivos. Comparar contra baseline (`/tmp/after.json`, estado pre-fix).
- [ ] Esperado: `fraseo_variado` sube hacia ~83% (cita_ok) por el gatillo general; sin regresión en off_corpus/relacional. Verificar a mano 3-4 fraseos.

---

## Self-Review
- Gatillo general (concepto, no fraseo) → Task 1. ✓ · inject lo usa → Task 2. ✓ · gold + medición → Task 3. ✓
- Legal-safe: disparo por match exacto normalizado contra datos curados (no fuzzy); respuesta = artículo curado. Difuso solo para *entender*.
- Riesgo: cambia el disparo para TODAS las queries → la re-eval valida no-regresión. `len(hits)!=1 → None` evita forzar en relacionales.
- Tipos: `find_subject_concept -> tuple[str,str,str,str,str|None] | None`, consumido igual en Task 2.
