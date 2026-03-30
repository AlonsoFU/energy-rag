#!/usr/bin/env python3
"""
Generar mapa de normas y vínculos en Markdown.
"""

import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def main():
    data = json.load(open("data/busquedas/normas_completas.json"))
    normas = {n['id_norma']: n for n in data['normas']}

    # Calcular estadísticas
    ids_existentes = set(normas.keys())
    todas_vinc = set()
    grafo = defaultdict(list)  # norma -> [normas que referencia]
    referenciada_por = defaultdict(list)  # norma -> [normas que la referencian]

    for n in normas.values():
        for v in n.get('vinculaciones_ids', []):
            if len(v) > 3:
                todas_vinc.add(v)
                grafo[n['id_norma']].append(v)
                referenciada_por[v].append(n['id_norma'])

    # Normas más referenciadas
    mas_referenciadas = sorted(referenciada_por.items(), key=lambda x: -len(x[1]))[:20]

    # Normas con más referencias salientes
    mas_referencias = sorted(grafo.items(), key=lambda x: -len(x[1]))[:20]

    # Por tipo
    por_tipo = defaultdict(list)
    for n in normas.values():
        por_tipo[n.get('tipo', 'OTRO')].append(n)

    # Por tema
    por_tema = defaultdict(list)
    for n in normas.values():
        for t in n.get('temas_detectados', []):
            por_tema[t].append(n)

    # Generar Markdown
    md = []
    md.append("# Mapa de Normas del Sector Eléctrico Chile")
    md.append(f"\n**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    md.append(f"\n**Total normas:** {len(normas)}")
    md.append(f"\n**Total vínculos:** {sum(len(v) for v in grafo.values())}")

    # Resumen visual
    md.append("\n\n## Resumen Estadístico")
    md.append("\n```")
    md.append(f"┌─────────────────────────────────────┐")
    md.append(f"│  NORMAS DESCARGADAS: {len(normas):>14} │")
    md.append(f"├─────────────────────────────────────┤")
    md.append(f"│  Leyes:     {len(por_tipo.get('LEY', [])):>24} │")
    md.append(f"│  Decretos:  {len(por_tipo.get('DECRETO', [])):>24} │")
    md.append(f"│  DFL:       {len(por_tipo.get('DFL', [])):>24} │")
    md.append(f"│  Otros:     {len(normas) - len(por_tipo.get('LEY', [])) - len(por_tipo.get('DECRETO', [])) - len(por_tipo.get('DFL', [])):>24} │")
    md.append(f"└─────────────────────────────────────┘")
    md.append("```")

    # Temas
    md.append("\n\n## Distribución por Tema")
    md.append("\n| Tema | Cantidad | Barra |")
    md.append("|------|----------|-------|")
    max_tema = max(len(v) for v in por_tema.values()) if por_tema else 1
    for tema, lista in sorted(por_tema.items(), key=lambda x: -len(x[1])):
        barra = "█" * int(len(lista) / max_tema * 20)
        md.append(f"| {tema} | {len(lista)} | {barra} |")

    # Normas más referenciadas (importantes)
    md.append("\n\n## Normas Más Referenciadas (Hub Central)")
    md.append("\nEstas normas son las más citadas por otras - son fundamentales:")
    md.append("\n| Norma | Referencias | Descripción |")
    md.append("|-------|-------------|-------------|")
    for id_n, refs in mas_referenciadas[:15]:
        if id_n in normas:
            n = normas[id_n]
            desc = n.get('titulo', '')[:50]
            md.append(f"| {n.get('tipo', '?')} {n.get('numero', '?')} | {len(refs)} | {desc}... |")
        else:
            md.append(f"| id:{id_n} | {len(refs)} | (no descargada) |")

    # Árbol de normas clave
    md.append("\n\n## Árbol de Normas Clave del Sector Eléctrico")
    md.append("\n```")
    md.append("LGSE (DFL 4/20.018) ─── Ley base del sector eléctrico")
    md.append("│")
    md.append("├── LEY 20.936 ─── Sistema de Transmisión")
    md.append("│   ├── Decreto 4T ─── Reglamento Transmisión")
    md.append("│   ├── Decreto 10 ─── Valorización")
    md.append("│   └── Decreto 37 ─── Peajes")
    md.append("│")
    md.append("├── DECRETO 62 ─── Transferencias de Potencia")
    md.append("│   ├── Decreto 44 ─── Modifica D.62")
    md.append("│   ├── Decreto 42 ─── Modifica D.62")
    md.append("│   └── Decreto 70 ─── Modifica D.62 (vigente)")
    md.append("│")
    md.append("├── DECRETO 113 ─── Servicios Complementarios")
    md.append("│   └── Decreto 130 ─── Modifica SSCC")
    md.append("│")
    md.append("└── DISTRIBUCIÓN")
    md.append("    ├── Ley 21.076 ─── Medidores")
    md.append("    └── Decreto 57 ─── Tarifas distribución")
    md.append("```")

    # Red de vínculos principales
    md.append("\n\n## Red de Vínculos (Top 30)")
    md.append("\nCada línea muestra: `Norma A → Norma B` (A referencia a B)")
    md.append("\n```")

    # Mostrar vínculos entre normas descargadas
    vinculos_mostrados = 0
    for id_origen, destinos in sorted(grafo.items(), key=lambda x: -len(x[1])):
        if vinculos_mostrados >= 30:
            break
        if id_origen in normas:
            n_origen = normas[id_origen]
            origen_str = f"{n_origen.get('tipo', '?')} {n_origen.get('numero', '?')}"
            for id_dest in destinos[:3]:
                if id_dest in normas:
                    n_dest = normas[id_dest]
                    dest_str = f"{n_dest.get('tipo', '?')} {n_dest.get('numero', '?')}"
                    md.append(f"{origen_str:20} → {dest_str}")
                    vinculos_mostrados += 1
                    if vinculos_mostrados >= 30:
                        break

    md.append("```")

    # Lista por tipo
    md.append("\n\n## Listado por Tipo")

    for tipo in ['DFL', 'LEY', 'DECRETO']:
        if tipo in por_tipo:
            md.append(f"\n### {tipo} ({len(por_tipo[tipo])})")
            md.append("\n| Número | ID BCN | Temas |")
            md.append("|--------|--------|-------|")
            for n in sorted(por_tipo[tipo], key=lambda x: str(x.get('numero', '')))[:30]:
                temas = ', '.join(n.get('temas_detectados', [])[:3])
                md.append(f"| {n.get('numero', '?')} | {n['id_norma']} | {temas} |")
            if len(por_tipo[tipo]) > 30:
                md.append(f"\n*... y {len(por_tipo[tipo]) - 30} más*")

    # Pendientes
    pendientes = todas_vinc - ids_existentes
    md.append(f"\n\n## Vinculaciones Pendientes ({len(pendientes)})")
    md.append("\nEstas normas son referenciadas pero no descargadas:")
    md.append(f"\n`{sorted(list(pendientes))[:20]}...`")

    # Guardar
    output_path = Path("data/busquedas/MAPA_NORMAS.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))

    print(f"Mapa generado: {output_path}")
    print(f"Total normas: {len(normas)}")
    print(f"Total vínculos: {sum(len(v) for v in grafo.values())}")


if __name__ == "__main__":
    main()
