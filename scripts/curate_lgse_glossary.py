"""Curate the LGSE's own defined terms as concepts + define_termino edges.

The eval category `lgse_definicional` surfaced that the law's fundamental
vocabulary (art 225 glossary: Autoproductor, Curva de carga, Confiabilidad,
Energía Firme… + the "Definición de X" articles) is NOT curated as concepts, so
those queries rely on raw retrieval (12/42 missed: the LLM cited a sibling
article, or art 225 didn't even surface). Curating them lets concept-injection
force the defining LGSE article to the top.

Source of truth = the law's own text (structural), NOT a model: each (term,
definición, artículo) comes from parsing art 225's `marcador) Término: def`
list and the `Artículo N°.- Definición de <Término>.` titled articles. For a
term already in the DB we only ADD the missing LGSE `define_termino` edge (then
`resolve_authority` lets the LEY win by rank); for a new term we INSERT the
concept too.

Run:  PYTHONPATH=. ./venv/bin/python scripts/curate_lgse_glossary.py --dry-run
      PYTHONPATH=. ./venv/bin/python scripts/curate_lgse_glossary.py --apply
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.connection import with_connection  # noqa: E402

LGSE_NORMA = "258171"
# A glossary entry: "marcador) Término: definición", definición up to the next
# marcador. Markers are single/double lowercase letters (a) … z) aa) …).
_ENTRY_SPLIT = re.compile(r"(?<=[\s.])([a-zñ]{1,2})\)\s+")
# Titled definition article: "Artículo N°.- Definición de <Término>. <cuerpo>"
_DEFART = re.compile(
    r"^\s*Art[íi]culo\s+\S+\s*\.?-?\s*Definici[óo]n\s+de\s+(.+?)\.\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def parse_lgse_terms(articulos: list[dict]) -> list[dict]:
    """[{term, definicion, articulo_id, numero}] from the LGSE's definitions."""
    out: list[dict] = []
    seen: set[str] = set()
    for a in articulos:
        raw = a["texto"] or ""
        flat = re.sub(r"\s+", " ", raw).strip()
        # Glossary list (art 225 et al.)
        parts = _ENTRY_SPLIT.split(flat)
        if len(parts) >= 5:  # has >= 2 markers → a list
            for i in range(1, len(parts) - 1, 2):
                m = re.match(r"([^:]{2,60}?):\s*(.+)", parts[i + 1])
                if not m:
                    continue
                term, definic = m.group(1).strip(), m.group(2).strip()
                if not (4 <= len(term) <= 60) or "," in term:
                    continue
                k = _norm(term)
                if k in seen:
                    continue
                seen.add(k)
                out.append({"term": term, "definicion": definic[:1200],
                            "articulo_id": a["id"], "numero": a["numero"]})
        # Titled definition article
        m = _DEFART.match(flat)
        if m:
            term, body = m.group(1).strip(), m.group(2).strip()
            if 4 <= len(term) <= 60 and "," not in term and _norm(term) not in seen:
                seen.add(_norm(term))
                out.append({"term": term, "definicion": body[:1200],
                            "articulo_id": a["id"], "numero": a["numero"]})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, numero, texto FROM articulos WHERE id_norma=%s", (LGSE_NORMA,))
        terms = parse_lgse_terms(cur.fetchall())
        cur.execute("SELECT id, nombre FROM conceptos")
        by_norm = {_norm(r["nombre"]): r["id"] for r in cur.fetchall()}

    new_concepts = [t for t in terms if _norm(t["term"]) not in by_norm]
    existing = [t for t in terms if _norm(t["term"]) in by_norm]
    print(f"LGSE términos definidos: {len(terms)} | ya conceptos: {len(existing)} "
          f"| nuevos a crear: {len(new_concepts)}")
    print("\nNUEVOS conceptos:")
    for t in new_concepts:
        print(f"  + art {t['numero']:<6} {t['term']:<42} :: {t['definicion'][:55]}…")
    print("\nEXISTENTES (solo +arista si falta):")
    for t in existing:
        print(f"  ~ art {t['numero']:<6} {t['term']}")

    if not args.apply:
        print("\n--dry-run: nada escrito. Usa --apply.")
        return

    ins_c = ins_e = skip_e = 0
    with with_connection() as conn, conn.cursor() as cur:
        for t in terms:
            cid = by_norm.get(_norm(t["term"]))
            if cid is None:
                cur.execute(
                    "INSERT INTO conceptos (nombre, definicion, metadata) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (t["term"], t["definicion"],
                     json.dumps({"source": "lgse_glossary", "domain": "electricidad"})),
                )
                cid = cur.fetchone()[0]
                ins_c += 1
            # idempotent define_termino edge: LGSE article → concept
            cur.execute(
                "SELECT 1 FROM referencias WHERE origen_articulo_id=%s "
                "AND destino_concepto_id=%s AND tipo_relacion='define_termino'",
                (t["articulo_id"], cid),
            )
            if cur.fetchone():
                skip_e += 1
                continue
            cur.execute(
                "INSERT INTO referencias (origen_articulo_id, destino_concepto_id, "
                "tipo_relacion, confianza, metodo_extraccion) "
                "VALUES (%s, %s, 'define_termino', 0.9, 'manual')",
                (t["articulo_id"], cid),
            )
            ins_e += 1
        conn.commit()
    print(f"\nInsertados: {ins_c} conceptos, {ins_e} aristas ({skip_e} ya existían).")


if __name__ == "__main__":
    main()
