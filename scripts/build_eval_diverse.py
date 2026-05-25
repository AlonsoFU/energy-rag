"""Build a broadly DIVERSE eval set to surface different classes of problems.

Unlike queries_balanced_v3 (all "qué es X" with canonical names, built from
our own define_termino edges → circular), this set deliberately stresses
DIFFERENT code paths, each tagged with its own `category` so behaviours are
measured separately (never aggregated into one number):

  definicional_canonico : baseline "qué es X" (continuity)
  fraseo_variado        : non-template phrasings → definitional detector robustness
  alias_sigla           : ask by alias/acronym → canonicalization + alias matching
  ambiguo               : bare word matching several concepts → ambiguity (B3)
  relacional            : multi-concept / multi-hop → GraphRAG territory (EXPECTED to
                          underperform today — we measure the gap, not hide it)
  natural               : real-user phrasing, not term lookup
  off_domain_corpus     : non-energy norms that ARE in the corpus
  off_corpus            : topics NOT in the corpus → must refuse

Rows: {query, category, expected_norma, expected_articulo, ambiguous?, note?}.
expected_* is null where there is no single ground-truth (relacional, ambiguo,
off_corpus, and most natural) — those are judged manually / measure behaviour.

Run:  PYTHONPATH=. ./venv/bin/python scripts/build_eval_diverse.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from psycopg.rows import dict_row
from src.pipelines.concept_injection import authoritative_pointer, definition_source_pointer
from src.storage.connection import with_connection


def _gold_pointer(metadata):
    """definition_source as gold ONLY when high-confidence (not needs_review).
    Tentative picks must NOT become gold — that would make the eval pass on an
    unconfirmed (possibly wrong) pick. Tentative → fall back to authority/fecha."""
    ds = (metadata or {}).get("definition_source")
    if ds and ds.get("needs_review") is False:
        return definition_source_pointer(metadata)
    return None

# Energy-domain normas (verified earlier) — keep in_domain categories clean.
ENERGY_NORMAS = ("1146553", "1112591", "250604", "1160108",
                 "1005169", "1183783", "1155887", "29819")

SQL_DEF = """
WITH ranked AS (
  SELECT c.nombre, c.aliases, c.metadata, a.id_norma, a.numero AS articulo,
         length(c.definicion) AS def_len,
         ROW_NUMBER() OVER (PARTITION BY c.id
           ORDER BY n.fecha_publicacion DESC NULLS LAST, a.id_norma, a.orden) AS rn
    FROM conceptos c
    JOIN referencias r ON r.destino_concepto_id=c.id AND r.tipo_relacion='define_termino'
    JOIN articulos a ON a.id=r.origen_articulo_id
    JOIN normas n ON n.id_norma=a.id_norma
   WHERE length(c.nombre) BETWEEN 4 AND 60
     AND a.id_norma = ANY(%s::text[])
)
SELECT nombre, aliases, metadata, id_norma, articulo FROM ranked WHERE rn=1
 ORDER BY def_len DESC LIMIT %s;
"""

# All alias→(norma,art) pairs in energy normas, independent of def length, so
# the alias_sigla category includes the key acronyms (CNE, SEC, SEN, CEN, …).
SQL_ALIAS = """
WITH ranked AS (
  SELECT c.nombre, c.aliases, c.metadata, a.id_norma, a.numero AS articulo,
         ROW_NUMBER() OVER (PARTITION BY c.id
           ORDER BY n.fecha_publicacion DESC NULLS LAST, a.id_norma, a.orden) AS rn
    FROM conceptos c
    JOIN referencias r ON r.destino_concepto_id=c.id AND r.tipo_relacion='define_termino'
    JOIN articulos a ON a.id=r.origen_articulo_id
    JOIN normas n ON n.id_norma=a.id_norma
   WHERE c.aliases IS NOT NULL AND array_length(c.aliases,1)>0
     AND a.id_norma = ANY(%s::text[])
)
SELECT nombre, aliases, metadata, id_norma, articulo FROM ranked WHERE rn=1;
"""

FRASEOS = (
    "a qué se refiere {x}",
    "cómo se define {x}",
    "qué se entiende por {x}",
    "explícame qué es {x}",
    "{x}",
)

# --- Hand-curated (NOT derived from our concept list → not circular) ---

AMBIGUO = [  # bare words known to map to >1 concept / domain
    "qué es Comité", "qué es Comisión", "qué es Coordinado",
    "qué es Escenario", "qué es el Ministerio", "qué significa Ley",
]

RELACIONAL = [
    "diferencia entre potencia firme y potencia inicial",
    "relación entre el Coordinador y la Comisión",
    "cómo se relaciona el Sistema de Transmisión con el de Distribución",
    "qué diferencia hay entre Obras Nuevas y Obras de Ampliación",
    "cómo interactúan la SEC y la CNE",
    "relación entre el Plan de Expansión y el Decreto de Expansión",
    "diferencia entre Sistema de Transmisión Nacional y Dedicado",
    "qué relación tiene el Panel de Expertos con el Coordinador",
    "cómo se vincula la Planificación Energética con la de la Transmisión",
    "diferencia entre cliente regulado y cliente libre",
    "qué normas regulan la transferencia de potencia entre generadores",
    "cómo se relacionan el VATT y el VI en la valorización",
]

NATURAL = [
    "¿quién fija las tarifas eléctricas en Chile?",
    "¿qué organismo fiscaliza a las empresas eléctricas?",
    "¿qué pasa si una distribuidora no cumple la normativa?",
    "¿quién opera el sistema eléctrico nacional?",
    "¿cómo se calcula el precio de nudo?",
    "¿qué se necesita para una concesión eléctrica?",
    "¿cómo se financia la expansión de la transmisión?",
    "¿qué derechos tiene un cliente eléctrico ante un corte?",
    "¿quién aprueba el plan de expansión de la transmisión?",
    "¿qué exige la ley de eficiencia energética a las empresas?",
    "¿cómo se sanciona a una empresa que incumple?",
    "¿qué es un sistema de almacenamiento de energía y cómo se remunera?",
]

OFF_DOMAIN_CORPUS = [  # in corpus, not energy
    ("qué es el telepeaje", "1207690"),
    ("qué dice la ley sobre el adelantamiento de vehículos", "1007469"),
    ("qué es una berma", "1007469"),
    ("qué es una calzada", "1007469"),
    ("cómo se reajustan los sueldos del sector público", "1199483"),
    ("qué es una bicicleta según la ley de tránsito", "1007469"),
]

OFF_CORPUS = [
    "qué es xenobalbúrgico", "cuál es la receta del pisco sour",
    "cómo se cura la diabetes tipo 1", "qué es la fotosíntesis",
    "biografía de Pablo Neruda", "horario del metro de Santiago",
    "qué es Bitcoin", "cómo se hace una empanada chilena",
    "cuál es la capital de Australia", "qué es el ratimagusto",
    "qué es la mecánica cuántica", "cómo se conjuga el verbo haber",
    "precio del dólar hoy", "qué es el yoga",
    "cuántos kilómetros mide la Gran Muralla China",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-def", type=int, default=30, help="distinct concepts for def/fraseo")
    ap.add_argument("--output", type=Path, default=Path("data/eval/queries_diverse.jsonl"))
    a = ap.parse_args()

    rows: list[dict] = []
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL_DEF, (list(ENERGY_NORMAS), a.n_def))
        concepts = cur.fetchall()

    # definicional_canonico (1 per concept) + fraseo_variado (subset × templates)
    for i, c in enumerate(concepts):
        # Authority-based gold: if B1 resolved an authoritative norm, use it
        # (the fecha-based pick is naive of legal rank). Single source of truth.
        ptr = _gold_pointer(c.get("metadata")) or authoritative_pointer(c.get("metadata"))
        norma, art = ptr if ptr else (c["id_norma"], str(c["articulo"]).strip())
        nm = c["nombre"].strip()
        rows.append({"query": f"qué es {nm}", "category": "definicional_canonico",
                     "expected_norma": norma, "expected_articulo": art})
        if i < 12:  # only first 12 get the phrasing fan-out (keeps set balanced)
            for tpl in FRASEOS:
                rows.append({"query": tpl.format(x=nm), "category": "fraseo_variado",
                             "expected_norma": norma, "expected_articulo": art})

    # alias_sigla: ask by each alias → same expected article as its concept.
    # Pulled independently (not def-len-gated) so key acronyms are included.
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL_ALIAS, (list(ENERGY_NORMAS),))
        alias_concepts = cur.fetchall()
    seen_alias: set[str] = set()
    for c in alias_concepts:
        ptr = _gold_pointer(c.get("metadata")) or authoritative_pointer(c.get("metadata"))
        norma, art = ptr if ptr else (c["id_norma"], str(c["articulo"]).strip())
        for alias in (c["aliases"] or []):
            alias = str(alias).strip()
            key = alias.lower()
            if 2 <= len(alias) <= 50 and key not in seen_alias:
                seen_alias.add(key)
                rows.append({"query": f"qué es {alias}", "category": "alias_sigla",
                             "expected_norma": norma, "expected_articulo": art,
                             "note": f"alias de «{c['nombre'].strip()}»"})

    for q in AMBIGUO:
        rows.append({"query": q, "category": "ambiguo", "expected_norma": None,
                     "expected_articulo": None, "ambiguous": True})
    for q in RELACIONAL:
        rows.append({"query": q, "category": "relacional", "expected_norma": None,
                     "expected_articulo": None, "note": "multi-concepto; esperado bajo hoy"})
    for q in NATURAL:
        rows.append({"query": q, "category": "natural", "expected_norma": None,
                     "expected_articulo": None})
    for q, norma in OFF_DOMAIN_CORPUS:
        rows.append({"query": q, "category": "off_domain_corpus",
                     "expected_norma": norma, "expected_articulo": None})
    for q in OFF_CORPUS:
        rows.append({"query": q, "category": "off_corpus", "expected_norma": None,
                     "expected_articulo": None})

    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_cat: dict[str, int] = {}
    for r in rows:
        by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
    print(f"escrito: {a.output} con {len(rows)} queries")
    for k, v in sorted(by_cat.items()):
        print(f"  {k:22}: {v}")


if __name__ == "__main__":
    main()
