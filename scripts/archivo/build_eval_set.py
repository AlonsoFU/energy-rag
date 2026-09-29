"""Build a real eval set for the Chilean electrical RAG.

Auto-generates `qué es <X>` and `definición de <X>` queries from conceptos that
have exactly one defining article in the DB, then appends a hand-curated tail
for diversity (negative, multi-norma, specific-article, tariff, etc.).

Each output line is a JSON object with keys:
    query, expected_norma, expected_articulo, category

`expected_norma` is an actual `id_norma` (BCN id, e.g. "1146553"). It can be
``null`` for negative/out-of-domain queries, in which case the runner expects
the system to refuse.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from psycopg.rows import dict_row

from src.storage.connection import with_connection


# Hand-curated diversity tail. Each entry MUST use real BCN ids that exist in
# the DB (verified at build time) — synthetic ids like "DECRETO_10" are a
# legacy mistake we are explicitly migrating away from.
HAND_CURATED: list[dict] = [
    # 1. Concept anchors verified manually end-to-end (these MUST work)
    {
        "query": "qué es C.O.M.A.",
        "expected_norma": "1146553",
        "expected_articulo": "49",
        "category": "concept_definition_manual",
    },
    {
        "query": "qué es V.A.T.T.",
        "expected_norma": "1146553",
        "expected_articulo": "50",
        "category": "concept_definition_manual",
    },
    {
        "query": "qué es potencia inicial",
        "expected_norma": "250604",
        "expected_articulo": "28",
        "category": "concept_definition_manual",
    },
    # 2. Specific-article lookup
    {
        "query": "Artículo 99 de la Ley 18410",
        "expected_norma": "29819",
        "expected_articulo": "99",
        "category": "specific_article",
    },
    # 3. Multi-norma — accept any norma about concesiones eléctricas; we use
    #    DFL 1 (id 1007469) which is the consolidated Ley General de Servicios
    #    Eléctricos in our DB.
    {
        "query": "qué leyes regulan las concesiones eléctricas",
        "expected_norma": "1007469",
        "expected_articulo": None,
        "category": "multi_norma",
    },
    # 4. Tariff
    {
        "query": "cómo se calcula el VATT",
        "expected_norma": "1146553",
        "expected_articulo": "50",
        "category": "tariff",
    },
    # 5. Coordinator
    {
        "query": "qué es el coordinador del sistema eléctrico",
        "expected_norma": "1146553",
        "expected_articulo": None,
        "category": "coordinator",
    },
    # 6. Power transfers
    {
        "query": "transferencias de potencia",
        "expected_norma": "250604",
        "expected_articulo": None,
        "category": "power_transfers",
    },
    # 7. Negatives — out-of-domain. The system must refuse with "no encuentro".
    {
        "query": "qué es xenobalbúrgico",
        "expected_norma": None,
        "expected_articulo": None,
        "category": "negative",
    },
    {
        "query": "cuál es la receta del pisco sour",
        "expected_norma": None,
        "expected_articulo": None,
        "category": "negative",
    },
]


SQL_AUTO_QUERIES = """
SELECT c.nombre,
       a.numero  AS articulo_numero,
       a.id_norma,
       n.clase,
       length(c.definicion) AS def_len
  FROM conceptos c
  JOIN referencias r ON r.destino_concepto_id = c.id
  JOIN articulos   a ON a.id = r.origen_articulo_id
  JOIN normas      n ON n.id_norma = a.id_norma
 WHERE c.id IN (
       SELECT c2.id
         FROM conceptos c2
         JOIN referencias r2 ON r2.destino_concepto_id = c2.id
        GROUP BY c2.id
       HAVING count(DISTINCT r2.origen_articulo_id) = 1
 )
   AND length(c.definicion) > 30
   AND length(c.nombre) BETWEEN 3 AND 60
   AND c.nombre NOT LIKE '%%clasificados%%'
 GROUP BY c.id, c.nombre, a.numero, a.id_norma, n.clase, c.definicion
 ORDER BY (n.clase = 'reglamento_base') DESC,
          length(c.definicion) DESC
 LIMIT %s;
"""


def fetch_auto_queries(limit: int) -> list[dict]:
    """Pull eval-suitable conceptos from the DB and shape them as eval rows.

    Each concepto we keep has exactly one defining article. We emit two query
    phrasings per concept-definition (`qué es <X>` and `definición de <X>`)
    only if `limit` is large enough to absorb both — otherwise just one.
    """
    rows: list[dict] = []
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL_AUTO_QUERIES, (limit * 2,))
        records = cur.fetchall()

    for rec in records:
        nombre = rec["nombre"].strip()
        rows.append({
            "query": f"qué es {nombre}",
            "expected_norma": rec["id_norma"],
            "expected_articulo": str(rec["articulo_numero"]).strip(),
            "category": "concept_definition_auto",
        })
    return rows


def verify_hand_curated() -> None:
    """Sanity-check that hand-curated norma ids exist in the DB.

    Raises a clear error if any hand-curated entry references a missing id —
    which would silently break the eval suite.
    """
    needed = {h["expected_norma"] for h in HAND_CURATED if h["expected_norma"]}
    if not needed:
        return
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id_norma FROM normas WHERE id_norma = ANY(%s::text[])",
            (list(needed),),
        )
        present = {r["id_norma"] for r in cur.fetchall()}
    missing = needed - present
    if missing:
        raise RuntimeError(
            f"Hand-curated eval references missing normas: {sorted(missing)}. "
            f"Update HAND_CURATED in build_eval_set.py."
        )


def build(limit: int, output: Path) -> int:
    """Build the eval set and write it as JSONL. Returns number of rows."""
    verify_hand_curated()

    auto_budget = max(0, limit - len(HAND_CURATED))
    auto_rows = fetch_auto_queries(auto_budget)[:auto_budget]

    rows = auto_rows + HAND_CURATED
    rows = rows[:limit]

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, default=50, help="max queries to emit")
    p.add_argument(
        "--output",
        type=Path,
        default=Path("data/eval/queries_chilean_electric.jsonl"),
        help="destination JSONL path",
    )
    p.add_argument(
        "--auto-only-output",
        type=Path,
        default=Path("data/eval/queries_auto.jsonl"),
        help="optional path to also dump auto-generated rows separately",
    )
    args = p.parse_args()

    # Side-output: auto-only rows (handy for inspection / diffing)
    verify_hand_curated()
    auto_only = fetch_auto_queries(max(0, args.limit - len(HAND_CURATED)))
    args.auto_only_output.parent.mkdir(parents=True, exist_ok=True)
    with args.auto_only_output.open("w", encoding="utf-8") as fh:
        for r in auto_only:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = build(args.limit, args.output)
    print(f"Wrote {n} queries to {args.output}")
    print(f"Wrote {len(auto_only)} auto-only queries to {args.auto_only_output}")


if __name__ == "__main__":
    main()
