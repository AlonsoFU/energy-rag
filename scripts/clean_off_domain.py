"""Move off-domain concepts out of glossary/concepts.yaml and delete from DB.

Off-domain secondaries to drop (decision 2026-05-11):
  - regulatorio_otros / concursal/ley_20720  (21)
  - regulatorio_otros / tránsito/ley_18290   (7)
  - regulatorio_otros / concesiones_viales/* (3)
  - indeterminado / no_aplica                (3)

Kept (in doubt, may apply to electrical):
  - regulatorio_otros / habilitaciones/ley_marco (16)

Output:
  - glossary/concepts.yaml             — only on-domain remain
  - glossary/incoming/off_domain.yaml  — archived off-domain entries
  - DB: DELETE FROM conceptos WHERE nombre IN (...)  (cascades to referencias)
"""
import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

DROP_SECONDARIES = {
    "concursal/ley_20720",
    "tránsito/ley_18290",
    "concesiones_viales/telepeaje",
    "concesiones_viales/dec_900",
    "concesiones_viales/sitio_unificado",
    "concesiones_viales/general",
    "no_aplica",
}

# Whitelist: these are misclassified by the initial domain extractor — they look
# off-domain by secondary but are actually electrical-regulation concepts. Keep
# them and (separately) reclassify to electricidad.
KEEP_DESPITE_SECONDARY = {
    "Obras de Ampliación",
    "Obras de Expansión",
    "Obras Nuevas",
    "Informe de Autorización de Conexión",
    "Costo de Falla de Corta Duración",
    "Costo de Falla de Larga Duración",
    "Valorización del Ajuste",
    "precalificación energética",
    "solución de conexión",
    "fecha de concreción de un proyecto",
}

# Reclassification targets for the whitelisted concepts
RECLASSIFY = {
    "Obras de Ampliación": ("electricidad", "transmisión/plan_expansión"),
    "Obras de Expansión": ("electricidad", "transmisión/plan_expansión"),
    "Obras Nuevas": ("electricidad", "transmisión/plan_expansión"),
    "Informe de Autorización de Conexión": ("electricidad", "distribución/conexión"),
    "Costo de Falla de Corta Duración": ("electricidad", "tarifas/general"),
    "Costo de Falla de Larga Duración": ("electricidad", "tarifas/general"),
    "Valorización del Ajuste": ("electricidad", "tarifas/general"),
    "precalificación energética": ("electricidad", "generación/general"),
    "solución de conexión": ("electricidad", "distribución/conexión"),
    "fecha de concreción de un proyecto": ("electricidad", "transmisión/plan_expansión"),
}


def is_off_domain(concept: dict) -> bool:
    name = concept.get("name", "")
    if name in KEEP_DESPITE_SECONDARY:
        return False
    dom = concept.get("domain") or {}
    primary = dom.get("primary")
    secondary = dom.get("secondary", "")
    if primary == "indeterminado":
        return True
    if primary == "regulatorio_otros" and secondary in DROP_SECONDARIES:
        return True
    return False


def reclassify(concept: dict) -> None:
    name = concept.get("name", "")
    if name in RECLASSIFY:
        primary, secondary = RECLASSIFY[name]
        concept["domain"] = {"primary": primary, "secondary": secondary}
        concept["domain_context"] = primary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    yaml_path = ROOT / "glossary" / "concepts.yaml"
    archive_path = ROOT / "glossary" / "incoming" / "off_domain.yaml"

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    concepts = data.get("concepts", [])
    # First, reclassify whitelisted concepts back to electricidad
    n_reclassified = 0
    for c in concepts:
        if c.get("name") in RECLASSIFY:
            reclassify(c)
            n_reclassified += 1
    print(f"Reclassified to electricidad: {n_reclassified}")

    on_domain = [c for c in concepts if not is_off_domain(c)]
    off_domain = [c for c in concepts if is_off_domain(c)]

    print(f"Total concepts: {len(concepts)}")
    print(f"  On-domain (kept):  {len(on_domain)}")
    print(f"  Off-domain (drop): {len(off_domain)}")

    if not off_domain:
        print("Nothing to do.")
        return

    print("\nOff-domain to remove:")
    for c in off_domain:
        sec = (c.get("domain") or {}).get("secondary", "?")
        print(f"  - {c['name']:<55} ({sec})")

    if args.dry_run:
        print("\n--dry-run: no changes.")
        return

    # Update main glossary
    data["concepts"] = on_domain
    data["total_concepts"] = len(on_domain)
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=120)
    print(f"\nWrote {yaml_path} ({len(on_domain)} concepts)")

    # Archive off-domain
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive = {
        "schema_version": 1,
        "archived_at": "2026-05-11",
        "reason": "Off-domain for energy-RAG (concursal/tránsito/concesiones_viales/indeterminado)",
        "total_concepts": len(off_domain),
        "concepts": off_domain,
    }
    with open(archive_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(archive, f, allow_unicode=True, sort_keys=False, width=120)
    print(f"Archived to {archive_path}")

    # Print names for DB cleanup
    print("\nNames to delete from DB:")
    for c in off_domain:
        print(c["name"])


if __name__ == "__main__":
    main()
