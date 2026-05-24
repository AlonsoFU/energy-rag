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
                continue
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
            tag = "OK alta" if not d["needs_review"] else "REVISAR baja"
            print(f"  [{tag}] {d['nombre'][:32]:32} -> {d['id_norma']} art {d['articulo']} "
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
    print(f"Escrito {len(review)} pendientes -> {REVIEW_PATH}")


if __name__ == "__main__":
    main()
