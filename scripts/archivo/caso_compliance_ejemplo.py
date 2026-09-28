#!/usr/bin/env python3
"""
Caso de uso: Análisis de compliance para un problema real.

Escenario:
Una empresa generadora quiere saber qué normas debe cumplir para:
1. Vender energía al mercado
2. Proveer servicios complementarios (SSCC)
3. Hacer transferencias de potencia

Este script encuentra las normas aplicables y sus relaciones.
"""

import json
from collections import defaultdict, Counter


def encontrar_normas_por_temas(normas, temas_requeridos):
    """
    Encuentra normas que contienen los temas especificados.
    """
    normas_aplicables = []

    for norma in normas.values():
        temas_norma = set(norma.get('temas_detectados', []))
        if temas_requeridos & temas_norma:  # Intersección
            normas_aplicables.append(norma)

    return normas_aplicables


def construir_grafo_vinculos(normas):
    """
    Construye un grafo de vinculaciones entre normas.
    """
    grafo = defaultdict(list)
    referencias_entrantes = defaultdict(list)

    for id_norma, norma in normas.items():
        for id_vinc in norma.get('vinculaciones_ids', []):
            if id_vinc in normas:
                grafo[id_norma].append(id_vinc)
                referencias_entrantes[id_vinc].append(id_norma)

    return grafo, referencias_entrantes


def encontrar_normas_relacionadas(norma_base, normas, grafo, nivel_max=2):
    """
    Encuentra normas relacionadas a una norma base (por vinculaciones).
    Usa BFS hasta nivel_max.
    """
    relacionadas = set()
    visitadas = set()
    cola = [(norma_base['id_norma'], 0)]  # (id, nivel)

    while cola:
        id_actual, nivel = cola.pop(0)

        if id_actual in visitadas or nivel > nivel_max:
            continue

        visitadas.add(id_actual)

        if nivel > 0:  # No incluir la norma base
            relacionadas.add(id_actual)

        # Expandir vinculaciones
        if id_actual in grafo:
            for id_vinc in grafo[id_actual]:
                if id_vinc not in visitadas:
                    cola.append((id_vinc, nivel + 1))

    return [normas[id_n] for id_n in relacionadas if id_n in normas]


def main():
    # Cargar normas
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    print("="*80)
    print("ANÁLISIS DE COMPLIANCE - Caso: Empresa Generadora")
    print("="*80)

    # === CASO: Empresa generadora ===

    print("\n📋 ESCENARIO:")
    print("   Una empresa generadora quiere cumplir normativa para:")
    print("   1. Vender energía al mercado")
    print("   2. Proveer servicios complementarios (SSCC)")
    print("   3. Hacer transferencias de potencia")

    # Buscar normas aplicables
    temas = {'ENERGIA', 'SSCC', 'TRANSFERENCIAS', 'GENERACION'}

    normas_aplicables = encontrar_normas_por_temas(normas, temas)

    print(f"\n✅ NORMAS APLICABLES ENCONTRADAS: {len(normas_aplicables)}")

    # Agrupar por tema
    por_tema = defaultdict(list)
    for norma in normas_aplicables:
        for tema in norma.get('temas_detectados', []):
            if tema in temas:
                por_tema[tema].append(norma)

    print(f"\nDesglose por tema:")
    for tema in sorted(temas):
        if tema in por_tema:
            print(f"  {tema:20} {len(por_tema[tema]):3} normas")

    # === NORMAS CLAVE ===

    print(f"\n{'='*80}")
    print("NORMAS CLAVE POR TEMA")
    print(f"{'='*80}")

    # Construir grafo
    grafo, refs_entrantes = construir_grafo_vinculos(normas)

    # Encontrar las más referenciadas de cada tema
    for tema in sorted(temas):
        if tema not in por_tema:
            continue

        print(f"\n🔹 {tema}:")

        # Ordenar por número de referencias entrantes
        normas_tema = por_tema[tema]
        normas_ordenadas = sorted(
            normas_tema,
            key=lambda n: len(refs_entrantes.get(n['id_norma'], [])),
            reverse=True
        )[:5]  # Top 5

        for i, norma in enumerate(normas_ordenadas, 1):
            id_n = norma['id_norma']
            refs = len(refs_entrantes.get(id_n, []))
            print(f"   {i}. {norma['tipo']} {norma['numero']:>6} (citada {refs:2} veces)")
            print(f"      {norma['titulo'][:75]}")
            print(f"      URL: https://www.bcn.cl/leychile/navegar?idNorma={id_n}")

    # === RED DE RELACIONES ===

    print(f"\n{'='*80}")
    print("RED DE RELACIONES - Decreto 113 (SSCC)")
    print(f"{'='*80}")

    # Buscar Decreto 113 (Servicios Complementarios)
    d113 = [n for n in normas.values() if n.get('tipo') == 'DECRETO' and n.get('numero') == '113']

    if d113:
        norma_base = d113[0]
        print(f"\n📍 NORMA BASE: {norma_base['tipo']} {norma_base['numero']}")
        print(f"   {norma_base['titulo'][:75]}")

        relacionadas = encontrar_normas_relacionadas(norma_base, normas, grafo, nivel_max=2)

        print(f"\n   Normas relacionadas (dentro de 2 niveles): {len(relacionadas)}")

        # Mostrar las con temas eléctricos
        relacionadas_electricas = [
            n for n in relacionadas
            if n.get('temas_detectados')
        ][:10]

        if relacionadas_electricas:
            print(f"\n   Top 10 relacionadas con temas eléctricos:")
            for i, norma in enumerate(relacionadas_electricas, 1):
                temas_str = ', '.join(norma.get('temas_detectados', [])[:3])
                print(f"      {i:2}. {norma['tipo']} {norma['numero']:>6} - {temas_str}")

    # === CADENAS DE MODIFICACIÓN ===

    print(f"\n{'='*80}")
    print("CADENAS DE MODIFICACIÓN - Decreto 62 (Transferencias)")
    print(f"{'='*80}")

    # Buscar Decreto 62
    d62 = [n for n in normas.values() if n.get('tipo') == 'DECRETO' and n.get('numero') == '62' and 'TRANSFERENCIAS' in n.get('temas_detectados', [])]

    if d62:
        norma_base = d62[0]
        id_d62 = norma_base['id_norma']

        print(f"\n📍 {norma_base['tipo']} {norma_base['numero']} - {norma_base['titulo'][:60]}")

        # Encontrar normas que lo referencian (posibles modificaciones)
        modificadores = refs_entrantes.get(id_d62, [])

        if modificadores:
            print(f"\n   Normas que referencian al D.62 ({len(modificadores)}):")

            for id_mod in modificadores[:10]:
                if id_mod in normas:
                    mod = normas[id_mod]
                    print(f"      • {mod['tipo']} {mod['numero']:>6} ({mod.get('numero', '?')})")
                    print(f"        {mod['titulo'][:75]}")

    # === POSIBLES FALENCIAS ===

    print(f"\n{'='*80}")
    print("ANÁLISIS DE POSIBLES FALENCIAS")
    print(f"{'='*80}")

    # Buscar normas huérfanas (sin referencias) con temas eléctricos
    normas_con_vinculos = set(grafo.keys()) | set(refs_entrantes.keys())

    huerfanas_electricas = [
        n for n in normas.values()
        if n['id_norma'] not in normas_con_vinculos
        and n.get('temas_detectados')
        and any(t in temas for t in n.get('temas_detectados', []))
    ]

    print(f"\n⚠️  Normas sin conexiones con otros (posibles gaps): {len(huerfanas_electricas)}")

    if huerfanas_electricas:
        print(f"\n   Ejemplos de normas aisladas:")
        for i, norma in enumerate(huerfanas_electricas[:5], 1):
            temas_str = ', '.join(norma.get('temas_detectados', []))
            print(f"      {i}. {norma['tipo']} {norma['numero']:>6} - {temas_str}")
            print(f"         {norma['titulo'][:75]}")
            print(f"         ⚠️  Esta norma NO tiene vinculaciones con otras")

    # === RECOMENDACIONES ===

    print(f"\n{'='*80}")
    print("💡 RECOMENDACIONES DE COMPLIANCE")
    print(f"{'='*80}")

    print(f"\n1. NORMAS FUNDAMENTALES A REVISAR:")
    print(f"   - DFL 4/2006 (Ley General de Servicios Eléctricos)")
    print(f"   - Decreto 113 (Reglamento SSCC)")
    print(f"   - Decreto 62 (Transferencias de Potencia) + modificaciones")

    print(f"\n2. CADENAS DE ACTUALIZACIÓN:")
    print(f"   - Verificar versiones vigentes (ej: D.62 → D.44 → D.42 → D.70)")

    print(f"\n3. NORMAS RELACIONADAS:")
    print(f"   - Explorar vínculos de 2° nivel para contexto completo")

    print(f"\n4. MONITOREO:")
    print(f"   - {len(huerfanas_electricas)} normas aisladas requieren verificación manual")

    # === GUARDAR ANÁLISIS ===

    analisis_compliance = {
        'escenario': 'Empresa generadora - Energía + SSCC + Transferencias',
        'normas_aplicables': len(normas_aplicables),
        'por_tema': {
            tema: len(lista) for tema, lista in por_tema.items()
        },
        'normas_clave': {
            tema: [
                {
                    'id': n['id_norma'],
                    'tipo': n['tipo'],
                    'numero': n['numero'],
                    'titulo': n['titulo'],
                    'referencias': len(refs_entrantes.get(n['id_norma'], [])),
                    'url': f"https://www.bcn.cl/leychile/navegar?idNorma={n['id_norma']}"
                }
                for n in sorted(
                    por_tema.get(tema, []),
                    key=lambda x: len(refs_entrantes.get(x['id_norma'], [])),
                    reverse=True
                )[:5]
            ]
            for tema in sorted(temas) if tema in por_tema
        },
        'posibles_falencias': [
            {
                'id': n['id_norma'],
                'tipo': n['tipo'],
                'numero': n['numero'],
                'titulo': n['titulo'],
                'temas': n.get('temas_detectados', []),
                'razon': 'Sin vinculaciones con otras normas'
            }
            for n in huerfanas_electricas[:20]
        ]
    }

    with open('data/busquedas/caso_compliance_generadora.json', 'w', encoding='utf-8') as f:
        json.dump(analisis_compliance, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"✅ Análisis guardado en: data/busquedas/caso_compliance_generadora.json")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
