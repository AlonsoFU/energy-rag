"""Round 3 alias curation — legal-safe additions only.

Adds aliases that are either:
  (A) Acronym formatting variants — same legal term, different punctuation
      (e.g. "C.O.M.A." ↔ "COMA"). 100% safe.
  (B) Morphological variants — singular/plural or qualifier-only forms
      VERIFIED to appear in the corpus, and unambiguous against other
      concepts in the same domain.

NOT included (legal-unsafe — judged manually):
  - Generic words (Cliente, Proyecto, Mora, Vivienda, Escenario, Ajustes)
  - "demanda máxima" ↔ Demanda de Punta (distinct concepts in LGSE)
  - "TAG" ↔ Multa TAG (TAG is the tax, not the fine)
  - "Convenio de Pago" ↔ Convenio de Pago de Multa TAG (genérico)
  - "cliente final" ↔ Usuario Final (could collide with concept Cliente)

Each entry has a reason comment for audit.

Run:
    python scripts/curate_round3_aliases.py --dry-run
    python scripts/curate_round3_aliases.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage.connection import with_connection


# Group A — acronym formatting variants (same term, different punctuation)
# All values are NEW aliases to add. Existing aliases are preserved.
PROMOTIONS_GROUP_A: dict[str, list[str]] = {
    "C.O.M.A.": ["COMA", "C.O.M.A"],                # corpus uses both (46/21 hits)
    "V.A.T.T.": ["VATT", "V.A.T.T"],                # corpus uses both (2/33 hits)
    "A.V.I.":   ["AVI", "A.V.I"],                   # corpus uses both (2/27 hits)
    "V.I.":     ["VI", "V.I"],                      # corpus uses both (68/84 hits)
    "PEAT":     ["P.E.A.T.", "P.E.A.T"],            # symmetry — user queries may use dots
    "PEBT":     ["P.E.B.T.", "P.E.B.T"],
    "DOL":      ["D.O.L.", "D.O.L"],
    "CDAT":     ["C.D.A.T.", "C.D.A.T"],
    "CDBT":     ["C.D.B.T.", "C.D.B.T"],
}

# Group B — morphological / qualifier-only variants verified in corpus
PROMOTIONS_GROUP_B: dict[str, list[str]] = {
    "Sistemas de Transmisión Zonal": [
        "Sistema de Transmisión Zonal",             # singular variant (16 hits)
        "transmisión zonal",                        # qualifier-only (29 hits)
    ],
    "Estado de Reserva Estratégica": [
        "reserva estratégica",                      # shortform (12 hits); unique in electric domain
    ],
    "Procedimiento sectorial": [
        "procedimientos sectoriales",               # plural (13 hits)
    ],
    "Órganos sectoriales": [
        "órgano sectorial",                         # singular (37 hits)
    ],
    "Declaración jurada": [
        "declaraciones juradas",                    # plural (10 hits)
    ],
    "Biocombustibles sólidos": [
        "biocombustible sólido",                    # singular (2 hits)
    ],
    "Iniciativas de Inversión": [
        "iniciativa de inversión",                  # singular (5 hits)
    ],
    "Planificación Energética": [
        "Planificación Energética de Largo Plazo",  # full official phrasing (7 hits)
        "PELP",                                     # standard acronym for the law
    ],
    "Costo de Falla de Corta Duración": [
        "CFCD",                                     # standard acronym (2 hits)
    ],
    "Costo de Falla de Larga Duración": [
        "CFLD",                                     # standard acronym (1 hit)
    ],
}


def _revert(all_promotions: dict[str, list[str]], dry_run: bool) -> None:
    """Remove exactly the Round-3 aliases (preserving any pre-existing ones).

    Used for clean A/B measurement: revert -> eval baseline -> re-apply.
    Idempotent: removing already-absent aliases is a no-op.
    """
    n_removed = 0
    with with_connection() as conn, conn.cursor() as cur:
        for concept_name, r3_aliases in all_promotions.items():
            cur.execute(
                "SELECT id, aliases FROM conceptos WHERE nombre = %s",
                (concept_name,),
            )
            row = cur.fetchone()
            if not row:
                continue
            cid, existing = row
            existing = list(existing) if existing else []
            r3_lower = {a.lower() for a in r3_aliases}
            kept = [a for a in existing if a.lower() not in r3_lower]
            removed = [a for a in existing if a.lower() in r3_lower]
            if not removed:
                continue
            print(f"[DEL]  {concept_name}: -{removed}  (keeping {kept})")
            n_removed += len(removed)
            if not dry_run:
                new_val = kept if kept else None
                cur.execute(
                    "UPDATE conceptos SET aliases = %s, updated_at = now() WHERE id = %s",
                    (new_val, cid),
                )
        if not dry_run:
            conn.commit()
    print(f"\nAliases removed: {n_removed}")
    if dry_run:
        print("--dry-run: no changes applied.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true",
                    help="Remove Round-3 aliases (for A/B baseline)")
    args = ap.parse_args()

    all_promotions = {**PROMOTIONS_GROUP_A, **PROMOTIONS_GROUP_B}

    if args.revert:
        _revert(all_promotions, args.dry_run)
        return

    n_concepts = 0
    n_aliases_added = 0
    n_already_present = 0

    with with_connection() as conn, conn.cursor() as cur:
        for concept_name, new_aliases in all_promotions.items():
            cur.execute(
                "SELECT id, aliases FROM conceptos WHERE nombre = %s",
                (concept_name,),
            )
            row = cur.fetchone()
            if not row:
                print(f"[SKIP] concept not in DB: {concept_name}")
                continue

            cid, existing = row
            existing = list(existing) if existing else []
            existing_lower = {a.lower() for a in existing}

            to_add = [a for a in new_aliases if a.lower() not in existing_lower]
            already = [a for a in new_aliases if a.lower() in existing_lower]

            if not to_add:
                print(f"[NOP]  {concept_name}: all aliases already present")
                n_already_present += len(already)
                continue

            merged = existing + to_add
            print(f"[ADD]  {concept_name}: +{to_add}")
            if existing:
                print(f"         (preserving existing: {existing})")
            n_concepts += 1
            n_aliases_added += len(to_add)
            n_already_present += len(already)

            if not args.dry_run:
                cur.execute(
                    "UPDATE conceptos SET aliases = %s, updated_at = now() WHERE id = %s",
                    (merged, cid),
                )

        if not args.dry_run:
            conn.commit()

    print()
    print(f"Concepts touched:      {n_concepts}")
    print(f"Aliases added:         {n_aliases_added}")
    print(f"Aliases already there: {n_already_present}")
    if args.dry_run:
        print("\n--dry-run: no changes applied.")


if __name__ == "__main__":
    main()
