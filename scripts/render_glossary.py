"""Render glossary/concepts.yaml → docs/glossary.md (human-readable view).

Auto-generated; do not edit docs/glossary.md by hand.
Run after editing concepts.yaml:
    python scripts/render_glossary.py
"""
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

DOMAIN_TITLES = {
    # Legacy flat domains (still supported for entries pre-hierarchy)
    "general": "Instituciones y términos generales",
    "transmisión": "Transmisión",
    "generación": "Generación y potencia",
    "tarifario": "Tarifas y peajes",
    "distribución": "Distribución y conexión",
    "renovables": "Renovables / biomasa",
    "concursal": "Procedimiento concursal (Ley 20.720)",
    "concesiones-viales": "Concesiones viales / Sitio Electrónico de Tarifas",
    "tránsito": "Tránsito (off-domain — revisar)",
    "gas": "Gas (no-eléctrico)",
    # New hierarchical primary domains
    "electricidad": "⚡ Electricidad",
    "regulatorio_otros": "📋 Otros dominios regulatorios",
    "energía_otra": "🔥 Otra energía (gas, etc.)",
    "indeterminado": "❓ Indeterminado / off-domain",
}

STATUS_BADGE = {
    "ok": "✅ ok",
    "corrected": "✏️ corrected",
    "needs_research": "🔍 needs_research",
    "not_reviewed": "⏳ not_reviewed",
}

CONFIDENCE_ICON = {"high": "🔒", "medium": "🟡", "low": "⚠️"}


def get_primary(c: dict) -> str:
    """Read primary domain from new hierarchical schema; fall back to legacy."""
    d = c.get("domain")
    if isinstance(d, dict):
        return d.get("primary") or "indeterminado"
    return c.get("domain_context") or "general"


def get_secondary(c: dict) -> str:
    d = c.get("domain")
    if isinstance(d, dict):
        return d.get("secondary") or "general"
    return ""


def render(concepts: list) -> str:
    by_primary = defaultdict(lambda: defaultdict(list))
    for c in concepts:
        primary = get_primary(c)
        secondary = get_secondary(c)
        by_primary[primary][secondary].append(c)

    out = []
    out.append("# Glosario — RAG normativa eléctrica chilena\n")
    out.append("> 🤖 **Auto-generado** desde `glossary/concepts.yaml`. NO editar este archivo a mano.\n")
    out.append("> Para editar: modificar `glossary/concepts.yaml`, después correr `python scripts/render_glossary.py`.\n")
    out.append("")
    out.append(f"**Total conceptos:** {len(concepts)}\n")

    # Stats summary
    n_validated_aliases = sum(
        1 for c in concepts for a in (c.get("aliases") or []) if a.get("validated")
    )
    n_total_aliases = sum(len(c.get("aliases") or []) for c in concepts)
    n_reviewed = sum(1 for c in concepts if c.get("status") in {"ok", "corrected"})
    out.append(f"- **Reviewed**: {n_reviewed} / {len(concepts)}")
    out.append(f"- **Validated aliases**: {n_validated_aliases} / {n_total_aliases}")
    out.append("")

    # Hierarchical render: primary → secondary → concepts
    PRIMARY_ORDER = ["electricidad", "energía_otra", "regulatorio_otros", "indeterminado"]
    primaries = [p for p in PRIMARY_ORDER if p in by_primary] + [
        p for p in by_primary if p not in PRIMARY_ORDER
    ]

    for primary in primaries:
        title = DOMAIN_TITLES.get(primary, primary.title())
        out.append(f"# {title}\n")
        n_in_primary = sum(len(v) for v in by_primary[primary].values())
        out.append(f"*({n_in_primary} conceptos)*\n")

        # Sort secondaries by total refs descending
        secondaries = sorted(
            by_primary[primary].keys(),
            key=lambda s: -sum(c.get("metadata", {}).get("refs_count") or 0 for c in by_primary[primary][s]),
        )
        for secondary in secondaries:
            sec_concepts = by_primary[primary][secondary]
            out.append(f"## {secondary} *({len(sec_concepts)})*\n")
            for c in sorted(sec_concepts, key=lambda x: -(x.get("metadata", {}).get("refs_count") or 0)):
                name = c["name"]
                status = c.get("status", "not_reviewed")
                badge = STATUS_BADGE.get(status, status)
                refs = c.get("metadata", {}).get("refs_count", 0)

                out.append(f"### {name}")
                out.append(f"**Status:** {badge} · **Refs:** {refs}\n")
                out.append(f"**Definición:**")
                out.append(f"> {c.get('definition', '').strip()}\n")

                # Source
                src = c.get("source") or {}
                if src.get("norm_id") and src.get("norm_id") != "unknown":
                    src_md = f"**Fuente:** [{src.get('norm_label', 'unknown')}, {src.get('article', '?')}]({src.get('url')})"
                else:
                    src_md = "**Fuente:** _no establecida_"
                out.append(src_md + "\n")

                # Aliases
                aliases = c.get("aliases") or []
                if aliases:
                    out.append("**Aliases:**\n")
                    for a in aliases:
                        icon = CONFIDENCE_ICON.get(a.get("confidence", "low"), "⚠️")
                        valid_mark = "✅" if a.get("validated") else "⏳"
                        out.append(f"- {icon} `{a['alias']}` — {a.get('confidence', 'low')}, {valid_mark}")
                    out.append("")
                else:
                    out.append("**Aliases:** _sin propuestas todavía_\n")

                # Relations
                rels = c.get("relations") or {}
                related = rels.get("related") or []
                broader = rels.get("broader") or []
                narrower = rels.get("narrower") or []
                if related or broader or narrower:
                    out.append("**Relaciones:**\n")
                    if related:
                        out.append(f"- related: {', '.join(related)}")
                    if broader:
                        out.append(f"- broader: {', '.join(broader)}")
                    if narrower:
                        out.append(f"- narrower: {', '.join(narrower)}")
                    out.append("")

                # Notes
                notes = (c.get("notes") or "").strip()
                if notes:
                    out.append(f"**Notas:** {notes}\n")
                difficulty = (c.get("extraction_difficulty") or "").strip()
                if difficulty:
                    out.append(f"**Dificultad de extracción:** {difficulty}\n")

                out.append("---\n")

    # Legend at bottom
    out.append("## Leyenda\n")
    out.append("**Status badges:**")
    for k, v in STATUS_BADGE.items():
        out.append(f"- {v} — `{k}`")
    out.append("")
    out.append("**Confidence icons (aliases):**")
    out.append("- 🔒 high — verificado en fuente oficial / uso establecido en industria")
    out.append("- 🟡 medium — uso plausible no verificado")
    out.append("- ⚠️ low — especulativo, requiere revisión")
    out.append("")
    out.append("**Validation:** ✅ = listo para cargar a DB · ⏳ = propuesto, sin validar.")
    out.append("")

    return "\n".join(out)


def main():
    yaml_path = ROOT / "glossary" / "concepts.yaml"
    md_path = ROOT / "docs" / "glossary.md"

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    concepts = data.get("concepts", [])
    md = render(concepts)
    md_path.write_text(md, encoding="utf-8")
    print(f"Wrote {md_path} ({len(md.splitlines())} lines, {len(concepts)} concepts)")


if __name__ == "__main__":
    main()
