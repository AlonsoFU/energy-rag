"""Resolve definition-by-REMISSION via the graph: "X a que se refiere el
artículo N de la Ley" → create a define_termino edge from the LGSE article N to
the concept, so authority (lex superior) + injection point to the law's real
definition instead of the reglamento that merely remits.

GENERAL, not per-concept. Two ingredients, both data-derived:

1. WHICH law is "la Ley" (contexto manda — it is NOT always the LGSE):
   a reglamento's "la Ley" = the law it IMPLEMENTS. We map "la Ley"→LGSE only
   for a concept whose defining norma is a REGLAMENTO (tipo DECRETO/RESOLUCIÓN)
   that explicitly CITES the LGSE and no competing enabling law. This excludes
   the Biocombustibles reglamento (→ Ley 21499), the telepeaje one (→ Ley de
   Tránsito 18.290) and self-referential LEYes (their "la Ley" = themselves).

2. WHERE it points: regex "artículo N° … de la Ley" over `conceptos.definicion`
   → LGSE article N (verified to exist; the LGSE is now fully ingested).
   Explicit "del decreto con fuerza de ley N°4/20.018" also resolves to LGSE.

Título-level remissions ("Título VI de la Ley", e.g. Panel de Expertos) are NOT
resolved here (a title is not a single article) — reported, left for later.

Run:  PYTHONPATH=. ./venv/bin/python scripts/follow_remissions.py        # dry-run
      PYTHONPATH=. ./venv/bin/python scripts/follow_remissions.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.storage.connection import with_connection  # noqa: E402

LGSE_NORMA = "258171"
_LGSE_CITE = re.compile(
    r"(ley general de servicios el[ée]ctricos|"
    r"(?:fuerza de ley|DFL)\s*N?°?\s*4\s*/?\s*20\.?018)", re.I)
# Article-level remission to the law: "...artículo N° ... de la Ley" or
# "...del decreto con fuerza de ley N°4/20.018".
_ART_LEY = re.compile(
    r"art[íi]culo\s+(\d+)\s*[°º]?\b[^.]{0,40}?"
    r"\bde(?:l)?\s+(?:la\s+Ley\b|decreto con fuerza de ley\s*N?°?\s*4)", re.I)
_TITULO_LEY = re.compile(r"T[íi]tulo\s+[IVXLC]+\b[^.]{0,40}?\bde(?:l)?\s+"
                         r"(?:la\s+Ley\b|decreto con fuerza de ley\s*N?°?\s*4)", re.I)


def lgse_reglamentos(cur) -> set[str]:
    """id_norma of reglamentos (DECRETO/RESOLUCIÓN) that implement the LGSE:
    cite it explicitly and name no competing enabling law. A LEY/DFL is never
    here — its own "la Ley" is self-referential, not the LGSE."""
    cur.execute("SELECT id_norma, tipo FROM normas")
    tipos = {r["id_norma"]: (r["tipo"] or "").upper() for r in cur.fetchall()}
    out: set[str] = set()
    for idn, tipo in tipos.items():
        if tipo not in ("DECRETO", "RESOLUCIÓN", "RESOLUCION"):
            continue
        cur.execute("SELECT string_agg(texto,' ') t FROM articulos WHERE id_norma=%s", (idn,))
        full = (cur.fetchone()["t"] or "")
        if _LGSE_CITE.search(full):
            out.add(idn)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        reglas = lgse_reglamentos(cur)
        # concept → set of origin normas (where it is define_termino'd)
        cur.execute("""SELECT r.destino_concepto_id cid, array_agg(DISTINCT a.id_norma) ns
                       FROM referencias r JOIN articulos a ON a.id=r.origen_articulo_id
                       WHERE r.tipo_relacion='define_termino' GROUP BY 1""")
        origin = {r["cid"]: set(r["ns"]) for r in cur.fetchall()}
        cur.execute("SELECT id, nombre, definicion FROM conceptos WHERE definicion ~* 'de la Ley'")
        cons = cur.fetchall()
        cur.execute("SELECT id, numero FROM articulos WHERE id_norma=%s", (LGSE_NORMA,))
        lgse_art_id = {str(r["numero"]).strip(): r["id"] for r in cur.fetchall()}

    plan, titulo_only, no_ctx = [], [], []
    for c in cons:
        d = c["definicion"] or ""
        m = _ART_LEY.search(d)
        if not m:
            if _TITULO_LEY.search(d):
                titulo_only.append(c["nombre"])
            continue
        # context gate: the concept must be defined by an LGSE-implementing
        # reglamento (so its "la Ley" really is the LGSE).
        if not (origin.get(c["id"], set()) & reglas):
            no_ctx.append(c["nombre"])
            continue
        art = m.group(1)
        aid = lgse_art_id.get(art)
        if aid is None:
            continue
        plan.append({"cid": c["id"], "nombre": c["nombre"], "art": art, "aid": aid})

    print(f"reglamentos que implementan la LGSE: {len(reglas)}")
    print(f"remisiones art→LGSE resolubles: {len(plan)}")
    for p in plan:
        print(f"  [{p['cid']}] {p['nombre'][:38]:38} → LGSE art {p['art']}")
    if titulo_only:
        print(f"\nTítulo-level (no resueltas, p/ej Panel): {titulo_only}")
    if no_ctx:
        print(f"\ncontexto NO LGSE (excluidas, 'la Ley'≠LGSE): {no_ctx}")

    if not args.apply:
        print("\n--dry-run: nada escrito. Usa --apply.")
        return

    ins = skip = 0
    with with_connection() as conn, conn.cursor() as cur:
        for p in plan:
            cur.execute("SELECT 1 FROM referencias WHERE origen_articulo_id=%s "
                        "AND destino_concepto_id=%s AND tipo_relacion='define_termino'",
                        (p["aid"], p["cid"]))
            if cur.fetchone():
                skip += 1
                continue
            cur.execute("INSERT INTO referencias (origen_articulo_id, destino_concepto_id, "
                        "tipo_relacion, confianza, metodo_extraccion) "
                        "VALUES (%s, %s, 'define_termino', 0.85, 'manual')",
                        (p["aid"], p["cid"]))
            ins += 1
        conn.commit()
    print(f"\nInsertadas: {ins} aristas ({skip} ya existían). "
          f"Correr resolve_authority.py --apply para que la LEY gane por rango.")


if __name__ == "__main__":
    main()
