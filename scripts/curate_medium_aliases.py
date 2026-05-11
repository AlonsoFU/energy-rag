"""Curate medium-confidence aliases in domain=electricidad.

Three actions per (concept, alias) decision:
  - PROMOTE: bump confidence to "high" + validated: true (obvious synonyms or
    confirmed via WebSearch against BCN/CNE/Coordinador)
  - REMOVE: drop the alias entirely (not a real alias, e.g. article+noun like
    "la Comisión", or a different concept incorrectly mapped)
  - KEEP: leave as medium (requires manual review)

Decisions are auditable below — each entry has a reason comment.

Run:
    python scripts/curate_medium_aliases.py --dry-run
    python scripts/curate_medium_aliases.py
"""
import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

# (concept_name, alias_string) → action
# Decisions audited 2026-05-04 with WebSearch where dudoso.
PROMOTE = {
    # Obvious synonyms / standard terminology in Chilean electrical regulation
    ("Ministerio", "MinEnergía"),                                          # common shortform
    ("Sistema de Transmisión", "transmisión eléctrica"),                   # direct synonym
    ("Sistema de Transmisión", "red de transmisión"),                      # direct synonym
    ("Empresa distribuidora", "empresa concesionaria"),                    # LGSE legal term
    ("Plan de Expansión", "plan anual de expansión"),                      # CNE official phrasing
    ("Panel", "Panel de Expertos Eléctrico"),                              # full name with qualifier
    ("Sistema Eléctrico Nacional", "Sistema Eléctrico Nacional Chileno"),  # variant w/ country
    ("Sistema de Transmisión Nacional", "transmisión troncal"),            # pre-LGSE-2016 term
    ("Sistema de Transmisión Nacional", "red troncal"),                    # pre-LGSE-2016 term
    ("Sistemas de Transmisión Dedicados", "transmisión dedicada"),         # direct synonym
    ("Empalme", "empalme eléctrico"),                                      # qualifier-only
    ("Biomasa", "biomasa sólida"),                                         # subset (most common)
    ("PNPP", "PNP promedio"),                                              # acronym variant
    ("PNPP", "precio nudo potencia"),                                      # full form
    ("PNEP", "PNE promedio"),                                              # acronym variant
    ("PNEP", "precio nudo energía"),                                       # full form
    ("Potencia Máxima", "capacidad nominal"),                              # technical equivalent
    ("Potencia Máxima", "potencia nominal"),                               # technical equivalent
    # Round 2 — second curation pass (2026-05-11)
    ("Adecuaciones", "adecuaciones de conexión"),                          # qualifier-only
    ("Obras Adicionales", "obras adicionales de conexión"),                # qualifier-only legal term
    ("Equipamiento de Generación Conjunto", "generación compartida"),       # direct synonym in PMGD
    ("Equipamiento de Generación Conjunto", "equipamiento conjunto"),       # shortform
    ("Capacidad Instalada Permitida", "capacidad permitida"),              # shortform of CIP
    ("Capacidad Instalada Permitida", "límite de capacidad de conexión"),  # operational synonym
    ("Cargos por Suministro Eléctrico", "cargos por suministro"),          # shortform
    ("Inyección de Excedentes Permitida", "inyección permitida"),          # shortform of IEP
    ("Sistema Eléctrico", "sistema eléctrico interconectado"),             # pre-LGSE-2016 term (SIC/SING era interconectado)
    ("AR", "Ajuste y Recargo"),                                            # full expansion of acronym
    ("AR", "ajuste o recargo"),                                            # case variant
}

REMOVE = {
    # Article + noun: these are in-text references, not aliases
    ("Comisión", "la Comisión"),
    ("Superintendencia", "la Superintendencia"),
    ("Coordinador", "el Coordinador"),
    ("Coordinador", "Coordinador del Sistema"),                            # descriptive phrase, not alias
    # WebSearch confirmed: "potencia inicial" is a DIFFERENT concept in D.S. 62
    # (defined as max_power × min_plant_factor for PV/wind), not a synonym of
    # Potencia de Suficiencia.
    ("Potencia de Suficiencia", "potencia inicial"),
    # Round 2 removals — not real aliases
    ("Capacidad Instalada", "kW instalados"),                              # unidad de medida, no alias
    ("Capacidad Instalada", "capacidad nominal del parque"),               # demasiado específico (parque solar/eólico)
    ("Biocombustibles sólidos", "combustibles sólidos"),                   # genérico — incluye carbón también
    ("Cargos por Suministro Eléctrico", "cargos tarifarios"),              # genérico — cualquier cargo tarifario, no este
    ("Capacidad de Inyección", "inyección máxima"),                         # contextual, no alias estable
    ("Inyección de Excedentes Permitida", "límite de inyección"),          # describe el límite, no es el concepto
    ("Obras Adicionales", "obras complementarias"),                        # concepto distinto en LGSE
}


def normalize(s: str) -> str:
    return (s or "").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    yaml_path = ROOT / "glossary" / "concepts.yaml"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    n_promoted = 0
    n_removed = 0
    n_kept_medium = 0
    touched_concepts = set()

    for c in data.get("concepts", []):
        dom = (c.get("domain") or {}).get("primary")
        if dom != "electricidad":
            continue

        name = c.get("name", "")
        new_aliases = []
        for a in c.get("aliases") or []:
            if a.get("confidence") != "medium":
                new_aliases.append(a)
                continue
            key = (normalize(name), normalize(a.get("alias", "")))
            if key in PROMOTE:
                a["confidence"] = "high"
                a["validated"] = True
                new_aliases.append(a)
                n_promoted += 1
                touched_concepts.add(name)
            elif key in REMOVE:
                n_removed += 1
                touched_concepts.add(name)
                # don't append → drop
            else:
                new_aliases.append(a)
                n_kept_medium += 1

        c["aliases"] = new_aliases

        # Flip status to ok for any concept now containing validated aliases
        if name in touched_concepts:
            has_validated = any(
                a.get("validated") for a in (c.get("aliases") or [])
            )
            if has_validated and c.get("status") not in {"ok", "corrected"}:
                c["status"] = "ok"

    print(f"Medium aliases promoted to high+validated: {n_promoted}")
    print(f"Medium aliases removed: {n_removed}")
    print(f"Medium aliases kept (still medium): {n_kept_medium}")
    print(f"Concepts touched: {len(touched_concepts)}")

    if args.dry_run:
        print("\n--dry-run: no changes written.")
        return

    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=120)
    print(f"\nWrote {yaml_path}")


if __name__ == "__main__":
    main()
