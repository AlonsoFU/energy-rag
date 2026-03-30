#!/usr/bin/env python3
"""
Analizador de casos complejos de POTENCIA.

Analiza un caso específico paso por paso y da sugerencias normativas.
"""

import json
from collections import defaultdict


def analizar_caso_potencia(descripcion_caso):
    """
    Analiza un caso de potencia y retorna sugerencias normativas paso por paso.
    """

    # Cargar normas
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    print("="*80)
    print("ANÁLISIS DE CASO - POTENCIA")
    print("="*80)
    print(f"\n📋 CASO PLANTEADO:")
    print(f"   {descripcion_caso}")

    # === PASO 1: IDENTIFICAR TEMAS RELACIONADOS ===

    print(f"\n{'='*80}")
    print("PASO 1: Identificar temas normativos relacionados")
    print("="*80)

    # Detectar palabras clave en el caso
    caso_lower = descripcion_caso.lower()

    temas_detectados = set()
    keywords_map = {
        'POTENCIA': ['potencia', 'suficiencia'],
        'TRANSFERENCIAS': ['transferencia', 'transferencias', 'pago', 'compensación'],
        'GENERACION': ['generador', 'generadora', 'central', 'planta'],
        'ENERGIA': ['energía', 'energia', 'venta', 'compra'],
        'SSCC': ['servicios complementarios', 'sscc', 'regulación', 'reserva'],
        'COORDINADOR': ['coordinador', 'cen', 'operación'],
        'TRANSMISION': ['transmisión', 'transmision', 'línea', 'subestación'],
        'DISTRIBUCION': ['distribución', 'distribucion', 'distribuidora'],
        'MEDICION': ['medición', 'medicion', 'medidor'],
        'TARIFAS': ['tarifa', 'precio', 'valorización']
    }

    for tema, keywords in keywords_map.items():
        for keyword in keywords:
            if keyword in caso_lower:
                temas_detectados.add(tema)

    print(f"\n✓ Temas identificados en el caso:")
    for tema in sorted(temas_detectados):
        print(f"   • {tema}")

    if not temas_detectados:
        temas_detectados = {'POTENCIA', 'TRANSFERENCIAS'}  # Default
        print(f"   • No se detectaron temas específicos, usando: POTENCIA, TRANSFERENCIAS")

    # === PASO 2: BUSCAR NORMAS APLICABLES ===

    print(f"\n{'='*80}")
    print("PASO 2: Buscar normas aplicables")
    print("="*80)

    # Buscar normas con los temas detectados
    normas_aplicables = []
    for norma in normas.values():
        temas_norma = set(norma.get('temas_detectados', []))
        if temas_detectados & temas_norma:  # Intersección
            normas_aplicables.append(norma)

    print(f"\n✓ {len(normas_aplicables)} normas aplicables encontradas")

    # Construir grafo de referencias
    grafo_refs = defaultdict(list)
    for n in normas.values():
        for vinc in n.get('vinculaciones_ids', []):
            if vinc in normas:
                grafo_refs[vinc].append(n['id_norma'])

    # Ordenar por relevancia (más citadas primero)
    normas_ordenadas = sorted(
        normas_aplicables,
        key=lambda n: len(grafo_refs.get(n['id_norma'], [])),
        reverse=True
    )

    # === PASO 3: NORMAS FUNDAMENTALES ===

    print(f"\n{'='*80}")
    print("PASO 3: Normas fundamentales (más citadas)")
    print("="*80)

    print(f"\nTop 10 normas más relevantes para este caso:")
    for i, norma in enumerate(normas_ordenadas[:10], 1):
        refs = len(grafo_refs.get(norma['id_norma'], []))
        temas = ', '.join(norma.get('temas_detectados', [])[:3])
        print(f"\n{i:2}. {norma['tipo']} {norma['numero']:>6} (citada {refs:2} veces)")
        print(f"    {norma['titulo'][:75]}")
        print(f"    Temas: {temas}")
        print(f"    URL: https://www.bcn.cl/leychile/navegar?idNorma={norma['id_norma']}")

    # === PASO 4: NORMA TÉCNICA ESPECÍFICA ===

    print(f"\n{'='*80}")
    print("PASO 4: Norma técnica específica (si aplica POTENCIA)")
    print("="*80)

    if 'POTENCIA' in temas_detectados or 'TRANSFERENCIAS' in temas_detectados:
        # Buscar D.62
        d62 = normas.get('250604')
        if d62:
            print(f"\n📌 DECRETO 62 - Reglamento de Transferencias de Potencia")
            print(f"   Título: APRUEBA REGLAMENTO DE TRANSFERENCIAS DE POTENCIA")
            print(f"   Fecha: 16-JUN-2006")
            print(f"   URL: https://www.bcn.cl/leychile/navegar?idNorma=250604")

            # Mostrar modificaciones
            refs_d62 = grafo_refs.get('250604', [])
            if refs_d62:
                print(f"\n   Modificado por:")
                for ref_id in refs_d62:
                    if ref_id in normas:
                        ref = normas[ref_id]
                        print(f"      • {ref['tipo']} {ref['numero']} - {ref['titulo'][:60]}")
                        print(f"        https://www.bcn.cl/leychile/navegar?idNorma={ref_id}")

    # === PASO 5: RECOMENDACIONES ESPECÍFICAS ===

    print(f"\n{'='*80}")
    print("PASO 5: Recomendaciones paso por paso")
    print("="*80)

    print(f"\n💡 SUGERENCIAS:")

    print(f"\n1. NORMATIVA BASE:")
    print(f"   ✓ Revisar DFL 4/2006 (Ley General de Servicios Eléctricos)")
    print(f"     - Marco legal general del sector")

    if 'POTENCIA' in temas_detectados or 'TRANSFERENCIAS' in temas_detectados:
        print(f"\n2. TRANSFERENCIAS DE POTENCIA:")
        print(f"   ✓ Decreto 62/2006 - Reglamento de Transferencias")
        print(f"     - Define metodología de cálculo")
        print(f"     - Establece procedimientos de pago")
        print(f"   ✓ Decreto 70/2024 - Última modificación vigente")
        print(f"     - Actualiza parámetros y procedimientos")

    if 'SSCC' in temas_detectados:
        print(f"\n3. SERVICIOS COMPLEMENTARIOS:")
        print(f"   ✓ Decreto 113/2019 - Reglamento SSCC")
        print(f"     - Regula prestación de servicios complementarios")

    if 'COORDINADOR' in temas_detectados:
        print(f"\n4. COORDINACIÓN:")
        print(f"   ✓ Verificar normativa del Coordinador Eléctrico Nacional")
        print(f"     - Procedimientos de operación")
        print(f"     - Normas técnicas (NTSyCS)")

    print(f"\n5. VERIFICACIÓN:")
    print(f"   ✓ Revisar cadena de modificaciones")
    print(f"     - Asegurar versión vigente de cada norma")
    print(f"   ✓ Consultar resoluciones técnicas de la CNE")
    print(f"   ✓ Revisar normativa técnica del Coordinador")

    # === PASO 6: CHECKLIST DE COMPLIANCE ===

    print(f"\n{'='*80}")
    print("PASO 6: Checklist de compliance")
    print("="*80)

    print(f"\n□ Identificar todas las normas aplicables (ver Paso 3)")
    print(f"□ Leer texto completo de normas fundamentales")
    print(f"□ Verificar versiones vigentes (modificaciones)")
    print(f"□ Revisar procedimientos del Coordinador")
    print(f"□ Consultar con asesor legal especializado")
    print(f"□ Documentar análisis y conclusiones")

    # === GUARDAR ANÁLISIS ===

    analisis_output = {
        'caso': descripcion_caso,
        'temas_detectados': list(temas_detectados),
        'normas_aplicables': len(normas_aplicables),
        'normas_clave': [
            {
                'id': n['id_norma'],
                'tipo': n['tipo'],
                'numero': n['numero'],
                'titulo': n['titulo'],
                'temas': n.get('temas_detectados', []),
                'referencias': len(grafo_refs.get(n['id_norma'], [])),
                'url': f"https://www.bcn.cl/leychile/navegar?idNorma={n['id_norma']}"
            }
            for n in normas_ordenadas[:15]
        ]
    }

    return analisis_output


if __name__ == "__main__":
    # CASO DE EJEMPLO
    caso = """
    Una central generadora de 200 MW instaló nuevos equipos de control que
    mejoraron su capacidad de suficiencia. El Coordinador reconoció esta mejora
    y ahora la central debe recibir pagos por transferencias de potencia mayores
    a las que recibía antes. La empresa quiere saber:
    1. Qué normativa aplica para el cálculo de estos pagos
    2. Cómo se determina la nueva suficiencia
    3. Qué procedimientos seguir ante el Coordinador
    4. Plazos y formalidades
    """

    resultado = analizar_caso_potencia(caso)

    with open('data/busquedas/analisis_caso_potencia.json', 'w', encoding='utf-8') as f:
        json.dump(resultado, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*80}")
    print(f"✅ Análisis guardado en: data/busquedas/analisis_caso_potencia.json")
    print(f"{'='*80}\n")
