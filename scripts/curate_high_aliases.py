"""Auto-validate high-confidence aliases in domain=electricidad.

Marks:
  - alias.validated = true
  - concept.status = "ok" (only for concepts that gained at least one validated alias)

Excludes a hand-picked list of false-positives (LLM confusions).

Run:
    python scripts/curate_high_aliases.py --dry-run
    python scripts/curate_high_aliases.py
"""
import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# (concept_name, alias_string) tuples to skip — known LLM confusions.
EXCLUDE = {
    # SIMCE = Sistema de Medición de la Calidad de la Educación (prueba escolar). Concepto
    # mal clasificado en domain=electricidad por el LLM; el alias en sí es correcto pero
    # el concepto no pertenece al glosario eléctrico.
    ("Sistema de Medición de la Calidad de la Educación", "SIMCE"),
    # V.I. demasiado genérico, choca con cualquier "v.i." en otros contextos
    ("Valores de Inversión", "V.I."),
    # pellets/leña/briquetas son TIPOS de biocombustible, no aliases del concepto general
    ("Biocombustibles sólidos", "pellets"),
    ("Biocombustibles sólidos", "leña"),
    ("Biocombustibles sólidos", "briquetas"),
    # RUT es universal (todo Chile), no eléctrico-específico. No aporta a queries del dominio.
    ("Rol Único Tributario", "RUT"),
}


def normalize(s: str) -> str:
    return (s or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Print plan, don't write")
    args = ap.parse_args()

    yaml_path = ROOT / "glossary" / "concepts.yaml"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    n_validated = 0
    n_skipped = 0
    n_concepts_ok = 0
    touched_concepts = []

    for c in data.get("concepts", []):
        dom = (c.get("domain") or {}).get("primary")
        if dom != "electricidad":
            continue

        name = c.get("name", "")
        aliases = c.get("aliases") or []
        gained_any = False

        for a in aliases:
            if a.get("confidence") != "high":
                continue
            key = (normalize(name), normalize(a.get("alias", "")))
            if key in EXCLUDE:
                n_skipped += 1
                continue
            if a.get("validated"):
                continue  # already validated, skip
            a["validated"] = True
            n_validated += 1
            gained_any = True

        if gained_any:
            # Only flip status if it was not already ok/corrected
            if c.get("status") not in {"ok", "corrected"}:
                c["status"] = "ok"
            n_concepts_ok += 1
            touched_concepts.append(name)

    print(f"Validated aliases: {n_validated}")
    print(f"Skipped (in EXCLUDE): {n_skipped}")
    print(f"Concepts marked status=ok: {n_concepts_ok}")
    print()
    print("Concepts touched:")
    for n in touched_concepts:
        print(f"  - {n}")

    if args.dry_run:
        print("\n--dry-run: no changes written.")
        return

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=120)
    print(f"\nWrote {yaml_path}")


if __name__ == "__main__":
    main()
