#!/usr/bin/env python3
"""
Analizar relaciones entre normas:
- Modificaciones (detectar en títulos)
- Cadenas de modificación
- Clusters temáticos
- Normas huérfanas
- Posibles inconsistencias
"""

import json
import re
from collections import defaultdict, Counter


def detectar_tipo_relacion(norma_origen, norma_destino):
    """
    Detectar el tipo de relación entre dos normas basándose en el título.
    """
    titulo = norma_origen.get('titulo', '').upper()

    # Patterns de modificación
    if 'MODIFICA' in titulo:
        return 'MODIFICA'
    if 'DEROGA' in titulo or 'DERÓGA' in titulo:
        return 'DEROGA'
    if 'SUSTITUYE' in titulo:
        return 'SUSTITUYE'
    if 'REGLAMENTA' in titulo or 'REGLAMENTO' in titulo:
        return 'REGLAMENTA'
    if 'APRUEBA' in titulo:
        return 'APRUEBA'

    return 'REFERENCIA'


def main():
    # Cargar datos
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    print(f"Analizando {len(normas):,} normas...\n")

    # === 1. CONSTRUIR GRAFO DE RELACIONES ===

    relaciones = []  # (id_origen, id_destino, tipo_relacion)
    referencias_por_norma = defaultdict(list)  # cuántas veces es referenciada

    for id_origen, norma_origen in normas.items():
        for id_destino in norma_origen.get('vinculaciones_ids', []):
            if id_destino in normas:
                tipo = detectar_tipo_relacion(norma_origen, normas[id_destino])
                relaciones.append((id_origen, id_destino, tipo))
                referencias_por_norma[id_destino].append((id_origen, tipo))

    print(f"✅ Relaciones detectadas: {len(relaciones):,}")

    # Contar por tipo
    tipos_count = Counter([r[2] for r in relaciones])
    print(f"\nPor tipo de relación:")
    for tipo, count in tipos_count.most_common():
        print(f"  {tipo:15} {count:4}")

    # === 2. DETECTAR MODIFICACIONES ===

    print(f"\n{'='*70}")
    print("MODIFICACIONES DETECTADAS")
    print(f"{'='*70}\n")

    modificaciones = [(o, d) for o, d, t in relaciones if t == 'MODIFICA']
    print(f"Total modificaciones: {len(modificaciones)}")

    # Mostrar las primeras 20
    print(f"\nPrimeras 20 modificaciones:")
    for i, (id_origen, id_destino) in enumerate(modificaciones[:20], 1):
        n_orig = normas[id_origen]
        n_dest = normas[id_destino]
        print(f"{i:2}. {n_orig['tipo']} {n_orig['numero']} MODIFICA → {n_dest['tipo']} {n_dest['numero']}")
        print(f"    {n_orig['titulo'][:80]}")

    # === 3. CADENAS DE MODIFICACIÓN ===

    print(f"\n{'='*70}")
    print("CADENAS DE MODIFICACIÓN")
    print(f"{'='*70}\n")

    # Encontrar normas que han sido modificadas múltiples veces
    normas_modificadas = defaultdict(list)
    for id_origen, id_destino in modificaciones:
        normas_modificadas[id_destino].append(id_origen)

    # Ordenar por número de modificaciones
    mas_modificadas = sorted(normas_modificadas.items(), key=lambda x: -len(x[1]))[:15]

    print("Normas más modificadas (top 15):")
    for id_norma, modificadores in mas_modificadas:
        n = normas[id_norma]
        print(f"\n{n['tipo']} {n['numero']} - {n['titulo'][:60]}")
        print(f"  Modificada {len(modificadores)} veces:")
        for id_mod in modificadores[:5]:  # Mostrar primeras 5
            mod = normas[id_mod]
            print(f"    ← {mod['tipo']} {mod['numero']} ({mod.get('numero', '?')})")
        if len(modificadores) > 5:
            print(f"    ... y {len(modificadores)-5} más")

    # === 4. CLUSTERS TEMÁTICOS ===

    print(f"\n{'='*70}")
    print("CLUSTERS TEMÁTICOS")
    print(f"{'='*70}\n")

    # Co-ocurrencia de temas
    tema_coocurrencia = defaultdict(lambda: defaultdict(int))

    for norma in normas.values():
        temas = norma.get('temas_detectados', [])
        for i, tema1 in enumerate(temas):
            for tema2 in temas[i+1:]:
                tema_coocurrencia[tema1][tema2] += 1
                tema_coocurrencia[tema2][tema1] += 1

    print("Co-ocurrencia de temas (top 15 pares):")
    pares = []
    for tema1, otros in tema_coocurrencia.items():
        for tema2, count in otros.items():
            if tema1 < tema2:  # Evitar duplicados
                pares.append((tema1, tema2, count))

    for tema1, tema2, count in sorted(pares, key=lambda x: -x[2])[:15]:
        print(f"  {tema1:15} + {tema2:15} = {count:4} normas")

    # === 5. NORMAS HUÉRFANAS ===

    print(f"\n{'='*70}")
    print("NORMAS HUÉRFANAS (sin referencias entrantes ni salientes)")
    print(f"{'='*70}\n")

    normas_con_vinculos_salientes = set(r[0] for r in relaciones)
    normas_con_vinculos_entrantes = set(r[1] for r in relaciones)

    huerfanas = []
    for id_norma, norma in normas.items():
        if id_norma not in normas_con_vinculos_salientes and id_norma not in normas_con_vinculos_entrantes:
            huerfanas.append(norma)

    print(f"Total huérfanas: {len(huerfanas)} ({len(huerfanas)/len(normas)*100:.1f}%)")

    # Mostrar algunas con temas eléctricos
    huerfanas_electricas = [n for n in huerfanas if n.get('temas_detectados')]
    print(f"Huérfanas con temas eléctricos: {len(huerfanas_electricas)}")

    print(f"\nPrimeras 10 huérfanas con temas eléctricos:")
    for i, norma in enumerate(huerfanas_electricas[:10], 1):
        temas = ', '.join(norma.get('temas_detectados', []))
        print(f"{i:2}. {norma['tipo']} {norma['numero']} - {temas}")
        print(f"    {norma['titulo'][:80]}")

    # === 6. NORMAS MÁS REFERENCIADAS ===

    print(f"\n{'='*70}")
    print("NORMAS MÁS REFERENCIADAS (Hub Central)")
    print(f"{'='*70}\n")

    mas_referenciadas = sorted(referencias_por_norma.items(), key=lambda x: -len(x[1]))[:15]

    print("Top 15 normas más citadas:")
    for id_norma, refs in mas_referenciadas:
        n = normas[id_norma]
        print(f"\n{n['tipo']} {n['numero']} - Citada {len(refs)} veces")
        print(f"  {n['titulo'][:80]}")

        # Contar tipos de relación
        tipos_rel = Counter([t for _, t in refs])
        print(f"  Relaciones: {dict(tipos_rel)}")

    # === 7. GUARDAR ANÁLISIS ===

    analisis = {
        'total_normas': len(normas),
        'total_relaciones': len(relaciones),
        'por_tipo': dict(tipos_count),
        'modificaciones': {
            'total': len(modificaciones),
            'normas_modificadas': len(normas_modificadas),
            'mas_modificadas': [
                {
                    'id': id_n,
                    'tipo': normas[id_n]['tipo'],
                    'numero': normas[id_n]['numero'],
                    'titulo': normas[id_n]['titulo'],
                    'veces_modificada': len(mods),
                    'modificadores': [
                        {'id': m, 'tipo': normas[m]['tipo'], 'numero': normas[m]['numero']}
                        for m in mods[:10]
                    ]
                }
                for id_n, mods in mas_modificadas[:20]
            ]
        },
        'huerfanas': {
            'total': len(huerfanas),
            'con_temas': len(huerfanas_electricas),
            'ejemplos': [
                {
                    'id': n['id_norma'],
                    'tipo': n['tipo'],
                    'numero': n['numero'],
                    'titulo': n['titulo'],
                    'temas': n.get('temas_detectados', [])
                }
                for n in huerfanas_electricas[:20]
            ]
        },
        'hubs': [
            {
                'id': id_n,
                'tipo': normas[id_n]['tipo'],
                'numero': normas[id_n]['numero'],
                'titulo': normas[id_n]['titulo'],
                'referencias': len(refs),
                'tipos_relacion': dict(Counter([t for _, t in refs]))
            }
            for id_n, refs in mas_referenciadas[:20]
        ]
    }

    with open('data/busquedas/analisis_relaciones.json', 'w', encoding='utf-8') as f:
        json.dump(analisis, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"✅ Análisis guardado en: data/busquedas/analisis_relaciones.json")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
