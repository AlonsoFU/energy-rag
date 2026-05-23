"""Curated concept-definition injection.

When a query matches a definitional pattern ("qué es X", "definición de X",
"qué significa X"), check if X exactly matches a curated concept name in the
DB. If so, force-inject its defining article at the top of the retrieved
docs — even if retrieval missed it in top-K.

Legal-safe by construction:
  - Match is strict-exact under deterministic normalization (case/tildes/
    acronym dots). No fuzzy, no thresholds.
  - The injected article comes from human-curated `referencias` edges, not
    from any model output.
  - We don't generate new content; we just reorder what the LLM sees.

Targets the structural blocker recall+art = 67% in_domain: in 1/3 of
in-domain queries the defining article doesn't reach the top-5 retrieved.
Curated injection fixes that for queries where we already know the answer.
"""
import re
from functools import lru_cache
from typing import Optional

from src.pipelines.normalize import normalize_for_match
from src.storage.connection import with_connection


# Match the term after a definitional opener. Greedy capture of the rest of
# the query (the term may contain spaces, dots, punctuation). The opener is
# stripped before normalization.
_DEFINITIONAL_PATTERN = re.compile(
    r"^\s*(?:qu[eé]\s+es|definici[oó]n\s+de|qu[eé]\s+significa|c[oó]mo\s+se\s+define)\s+(.+?)\s*[?¿]*\s*$",
    re.IGNORECASE,
)


def extract_definitional_term(query: str) -> Optional[str]:
    """Return X if query is `qué es X` / `definición de X` / ... Else None."""
    m = _DEFINITIONAL_PATTERN.match(query)
    return m.group(1).strip() if m else None


@lru_cache(maxsize=1)
def _concept_index() -> dict[str, tuple[str, str, str, str]]:
    """Build a `{normalized_name_or_alias: (id_norma, articulo_numero,
    definicion, nombre_canonico)}` map.

    Cached in-process. Reading the whole table is cheap (~thousands of rows)
    and avoids a DB roundtrip on every query. If a concept has multiple
    defining articles, we keep the FIRST one returned by ORDER BY — strictly
    deterministic across runs. `definicion` is the curated glossary text;
    `nombre_canonico` lets the inject detect when the query used an alias
    (key != canonical) and surface the alias→canonical link.
    """
    out: dict[str, tuple[str, str, str, str]] = {}
    with with_connection() as conn, conn.cursor() as cur:
        # ONLY define_termino edges — true definitions, not mentions/citations
        # (the 'cita' edges point to articles that merely use the term).
        # Ordered by fecha_publicacion DESC so when a term is defined in
        # several normas, the MOST RECENT (vigente) definition wins. NULLS
        # LAST so dated normas beat undated ones.
        cur.execute(
            """
            SELECT c.nombre, a.id_norma, a.numero, c.definicion
              FROM conceptos c
              JOIN referencias r ON r.destino_concepto_id = c.id
                                AND r.tipo_relacion = 'define_termino'
              JOIN articulos a ON a.id = r.origen_articulo_id
              JOIN normas n ON n.id_norma = a.id_norma
             ORDER BY c.nombre, n.fecha_publicacion DESC NULLS LAST,
                      a.id_norma, a.numero
            """
        )
        for nombre, id_norma, articulo, definicion in cur.fetchall():
            key = normalize_for_match(nombre)
            # Keep FIRST per concept = most recent definition (vigencia).
            if key and key not in out:
                out[key] = (str(id_norma), str(articulo), definicion or "", nombre)
        # Aliases → same most-recent defining article.
        cur.execute(
            """
            SELECT c.nombre, c.aliases, a.id_norma, a.numero, c.definicion
              FROM conceptos c
              JOIN referencias r ON r.destino_concepto_id = c.id
                                AND r.tipo_relacion = 'define_termino'
              JOIN articulos a ON a.id = r.origen_articulo_id
              JOIN normas n ON n.id_norma = a.id_norma
             WHERE c.aliases IS NOT NULL
             ORDER BY c.nombre, n.fecha_publicacion DESC NULLS LAST,
                      a.id_norma, a.numero
            """
        )
        for _nombre, aliases, id_norma, articulo, definicion in cur.fetchall():
            for alias in (aliases or []):
                key = normalize_for_match(str(alias))
                if key and key not in out:
                    out[key] = (str(id_norma), str(articulo), definicion or "", _nombre)
    return out


def find_curated_definition(query: str) -> Optional[tuple[str, str, str, str]]:
    """Return `(id_norma, articulo_numero, definicion, nombre_canonico)` if the
    query's term matches a curated concept; else None. No fuzzy.
    """
    term = extract_definitional_term(query)
    if term is None:
        return None
    key = normalize_for_match(term)
    if not key:
        return None
    return _concept_index().get(key)


def fetch_article_doc(id_norma: str, articulo_numero: str) -> Optional[dict]:
    """Load a single article doc shaped like the retrieval pipeline emits.

    Returns the same keys downstream code expects (`id_norma`, `articulo_numero`,
    `articulo_text`, `contextual_text`, `score`). Score is high so callers can
    place this at the top of the pool deterministically.
    """
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.id_norma, a.numero, a.texto
              FROM articulos a
             WHERE a.id_norma = %s AND a.numero = %s
             LIMIT 1
            """,
            (id_norma, articulo_numero),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "id_norma": str(row[0]),
            "articulo_numero": str(row[1]),
            "articulo_text": row[2] or "",
            "contextual_text": row[2] or "",  # ranker-side enrichment not needed
            "score": 9999.0,  # marker: forced-injection, top of pool
            "_injected": True,
        }


def _focused_doc(id_norma: str, articulo: str, definicion: str) -> dict:
    """A doc whose body is the FOCUSED curated definition, labeled with the
    real defining article's citation header. Co-locating the verbatim
    definition with `[Art. N de ID]` lets the model copy the correct citation
    instead of attaching it to a tighter sibling article in the pool."""
    return {
        "id_norma": str(id_norma),
        "articulo_numero": str(articulo),
        "articulo_text": definicion,
        "contextual_text": definicion,
        "score": 9999.0,
        "_injected": True,
        "_focused": True,
    }


def _alias_link_doc(alias: str, canonical: str, definicion: str,
                    id_norma: str, articulo: str) -> dict:
    """A doc that states the alias→canonical link explicitly, so the literal
    query token (the alias the user typed, e.g. "SEC") appears in the context.

    When a user asks "qué es SEC", the defining article only contains the
    EXPANSION ("Superintendencia de Electricidad y Combustibles"), not "SEC".
    The LLM, under strict grounding, then cannot anchor "SEC" and refuses
    (root-caused 2026-05-23). Surfacing the link — verbatim from curated alias
    data — lets it answer and cite the real article."""
    text = f"«{alias}» se refiere a «{canonical}». {definicion}".strip()
    return {
        "id_norma": str(id_norma),
        "articulo_numero": str(articulo),
        "articulo_text": text,
        "contextual_text": text,
        "score": 9999.0,
        "_injected": True,
        "_alias_link": True,
    }


def inject_definition(query: str, docs: list[dict]) -> list[dict]:
    """If query is definitional and we have a curated answer, prepend the
    defining article to `docs` (deduped by (id_norma, articulo_numero)).

    Special case — ALIAS queries: if the user typed an alias/acronym (the
    matched term differs from the concept's canonical name), inject a chunk
    that states the alias→canonical link explicitly, so the literal query
    token is present in the context (otherwise the LLM refuses — see
    `_alias_link_doc`). This is scoped to alias queries, so it does not affect
    canonical-name queries (and thus carries no entity-collision regression
    risk).

    With `inject_focused_definition` (default off), the injected body is the
    curated definition text rather than the full — possibly glossary-sized —
    article, and any full copy of that article in the pool is REPLACED.

    Returns the same list type. If no injection applies, returns docs unchanged.
    """
    hit = find_curated_definition(query)
    if hit is None:
        return docs
    id_norma, articulo, definicion, canonical = hit

    # Alias query? The matched term (what the user typed) differs from the
    # concept's canonical name under orthographic normalization.
    term = extract_definitional_term(query)
    is_alias = bool(term and canonical
                    and normalize_for_match(term) != normalize_for_match(canonical))
    if is_alias and definicion.strip():
        rest = [
            d for d in docs
            if not (str(d.get("id_norma")) == id_norma
                    and str(d.get("articulo_numero")) == articulo)
        ]
        return [_alias_link_doc(term.strip(), canonical, definicion,
                                id_norma, articulo)] + rest

    # Lazy import keeps this module import-cheap and avoids a cycle.
    from src.core import config as _cfg
    focused = bool(getattr(_cfg.settings, "inject_focused_definition", False)
                   and definicion.strip())

    if focused:
        # Drop any existing copy of the defining article (full or not) so its
        # citation header isn't duplicated, then prepend the focused chunk.
        rest = [
            d for d in docs
            if not (str(d.get("id_norma")) == id_norma
                    and str(d.get("articulo_numero")) == articulo)
        ]
        return [_focused_doc(id_norma, articulo, definicion)] + rest

    # Non-focused (legacy): move existing full article to front, or fetch it.
    for i, d in enumerate(docs):
        if (str(d.get("id_norma")) == id_norma
                and str(d.get("articulo_numero")) == articulo):
            if i == 0:
                return docs  # already at top
            return [d] + docs[:i] + docs[i + 1:]
    new_doc = fetch_article_doc(id_norma, articulo)
    if new_doc is None:
        return docs  # curation references a missing article — fail open
    return [new_doc] + docs
