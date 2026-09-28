#!/usr/bin/env python3
"""
Análisis de relaciones implícitas:
- Co-ocurrencia temática
- Clusters de normas relacionadas
- Detección de patrones
"""

import json
from collections import defaultdict, Counter


def main():
    # Cargar normas
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    print("="*80)
    print("ANÁLISIS DE RELACIONES IMPLÍCITAS Y CLUSTERS")
    print("="*80)

    # === 1. CO-OCURRENCIA TEMÁTICA ===

    print("\n📊 CO-OCURRENCIA TEMÁTICA")
    print("="*80)
    print("Temas que aparecen juntos en las mismas normas:")

    coocurrencia = defaultdict(lambda: defaultdict(int))

    for norma in normas.values():
        temas = norma.get('temas_detectados', [])
        for i, tema1 in enumerate(temas):
            for tema2 in temas[i+1:]:
                coocurrencia[tema1][tema2] += 1
                coocurrencia[tema2][tema1] += 1

    # Ordenar pares por frecuencia
    pares = []
    for tema1, otros in coocurrencia.items():
        for tema2, count in otros.items():
            if tema1 < tema2:  # Evitar duplicados
                pares.append((tema1, tema2, count))

    print(f"\nTop 20 pares de temas:")
    for i, (tema1, tema2, count) in enumerate(sorted(pares, key=lambda x: -x[2])[:20], 1):
        print(f"{i:2}. {tema1:15} + {tema2:15} = {count:3} normas")

    # Interpretación
    print(f"\n💡 INTERPRETACIÓN:")
    top_par = sorted(pares, key=lambda x: -x[2])[0]
    print(f"   • El par más frecuente es {top_par[0]} + {top_par[1]} ({top_par[2]} normas)")
    print(f"   • Esto sugiere que ambos temas están estrechamente relacionados")

    # === 2. CLUSTERS TEMÁTICOS ===

    print(f"\n{'='*80}")
    print("🔍 CLUSTERS TEMÁTICOS (Grupos de normas relacionadas)")
    print("="*80)

    # Definir clusters conocidos
    clusters = {
        'Transmisión Sistema': {'TRANSMISION', 'PEAJES', 'TARIFAS'},
        'Generación y Venta': {'GENERACION', 'ENERGIA', 'POTENCIA'},
        'Distribución': {'DISTRIBUCION', 'MEDICION', 'TARIFAS'},
        'Operación Sistema': {'SSCC', 'COORDINADOR', 'TRANSFERENCIAS'}
    }

    for nombre_cluster, temas_cluster in clusters.items():
        normas_cluster = []

        for norma in normas.values():
            temas_norma = set(norma.get('temas_detectados', []))
            if len(temas_norma & temas_cluster) >= 2:  # Al menos 2 temas del cluster
                normas_cluster.append(norma)

        print(f"\n🔹 Cluster: {nombre_cluster}")
        print(f"   Temas: {', '.join(temas_cluster)}")
        print(f"   Normas en este cluster: {len(normas_cluster)}")

        if normas_cluster:
            # Mostrar las más referenciadas
            grafo_refs = defaultdict(list)
            for n in normas.values():
                for vinc in n.get('vinculaciones_ids', []):
                    if vinc in normas:
                        grafo_refs[vinc].append(n['id_norma'])

            normas_ordenadas = sorted(
                normas_cluster,
                key=lambda n: len(grafo_refs.get(n['id_norma'], [])),
                reverse=True
            )[:5]

            print(f"\n   Top 5 normas del cluster:")
            for i, norma in enumerate(normas_ordenadas, 1):
                refs = len(grafo_refs.get(norma['id_norma'], []))
                temas_str = ', '.join(norma.get('temas_detectados', [])[:3])
                print(f"      {i}. {norma['tipo']} {norma['numero']:>6} ({refs:2} refs) - {temas_str}")

    # === 3. PATRONES DE TIPO DE NORMA POR TEMA ===

    print(f"\n{'='*80}")
    print("📋 PATRONES: Tipo de norma predominante por tema")
    print("="*80)

    tipo_por_tema = defaultdict(lambda: defaultdict(int))

    for norma in normas.values():
        tipo = norma.get('tipo', 'DESCONOCIDO')
        for tema in norma.get('temas_detectados', []):
            tipo_por_tema[tema][tipo] += 1

    temas_principales = ['TRANSMISION', 'GENERACION', 'DISTRIBUCION', 'SSCC', 'MEDICION']

    for tema in temas_principales:
        if tema in tipo_por_tema:
            tipos = tipo_por_tema[tema]
            total = sum(tipos.values())

            print(f"\n🔹 {tema} ({total} normas):")
            for tipo, count in sorted(tipos.items(), key=lambda x: -x[1])[:3]:
                porcentaje = (count / total) * 100
                print(f"      {tipo:12} {count:3} ({porcentaje:5.1f}%)")

            # Interpretación
            tipo_dominante = max(tipos.items(), key=lambda x: x[1])
            if tipo_dominante[1] > total * 0.6:
                print(f"      💡 Dominado por {tipo_dominante[0]}s ({tipo_dominante[1]/total*100:.0f}%)")

    # === 4. DETECCIÓN DE FALENCIAS (Gaps) ===

    print(f"\n{'='*80}")
    print("⚠️  DETECCIÓN DE POSIBLES FALENCIAS NORMATIVAS")
    print("="*80)

    # Buscar combinaciones de temas con pocas normas
    print(f"\nCombinaciones de temas con BAJA cobertura (< 10 normas):")

    pares_bajos = [(t1, t2, c) for t1, t2, c in pares if c < 10]

    for i, (tema1, tema2, count) in enumerate(sorted(pares_bajos, key=lambda x: x[2])[:10], 1):
        print(f"   {i:2}. {tema1:15} + {tema2:15} = {count:2} normas ⚠️  Gap potencial")

    # === 5. NORMAS MULTI-TEMA (Normas integradoras) ===

    print(f"\n{'='*80}")
    print("🌐 NORMAS INTEGRADORAS (Multi-tema)")
    print("="*80)

    normas_multi = [
        n for n in normas.values()
        if len(n.get('temas_detectados', [])) >= 5
    ]

    normas_multi.sort(key=lambda n: -len(n.get('temas_detectados', [])))

    print(f"\nNormas que abarcan 5+ temas ({len(normas_multi)} total):")
    for i, norma in enumerate(normas_multi[:10], 1):
        temas = norma.get('temas_detectados', [])
        print(f"\n   {i:2}. {norma['tipo']} {norma['numero']} ({len(temas)} temas)")
        print(f"       {norma['titulo'][:75]}")
        print(f"       Temas: {', '.join(temas)}")

    print(f"\n   💡 Estas normas son 'integradoras' - abarcan múltiples aspectos del sector")

    # === GUARDAR ANÁLISIS ===

    analisis = {
        'coocurrencia': {
            'top_pares': [
                {'tema1': t1, 'tema2': t2, 'count': c}
                for t1, t2, c in sorted(pares, key=lambda x: -x[2])[:20]
            ]
        },
        'clusters': {
            nombre: {
                'temas': list(temas_cluster),
                'total_normas': len([
                    n for n in normas.values()
                    if len(set(n.get('temas_detectados', [])) & temas_cluster) >= 2
                ])
            }
            for nombre, temas_cluster in clusters.items()
        },
        'falencias_potenciales': [
            {'tema1': t1, 'tema2': t2, 'normas': c, 'nivel': 'CRITICO' if c < 5 else 'MODERADO'}
            for t1, t2, c in sorted(pares_bajos, key=lambda x: x[2])[:20]
        ],
        'normas_integradoras': [
            {
                'id': n['id_norma'],
                'tipo': n['tipo'],
                'numero': n['numero'],
                'titulo': n['titulo'],
                'temas': n.get('temas_detectados', []),
                'num_temas': len(n.get('temas_detectados', []))
            }
            for n in normas_multi[:20]
        ]
    }

    with open('data/busquedas/analisis_clusters_implicitos.json', 'w', encoding='utf-8') as f:
        json.dump(analisis, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"✅ Análisis guardado en: data/busquedas/analisis_clusters_implicitos.json")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
