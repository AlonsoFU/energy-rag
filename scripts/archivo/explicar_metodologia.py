#!/usr/bin/env python3
"""
Explicación de la metodología de búsqueda y sus limitaciones.
"""

import json

print("="*80)
print("METODOLOGÍA DE BÚSQUEDA - Cómo funciona y qué tan confiable es")
print("="*80)

# Cargar normas
with open('data/busquedas/normas_completas.json') as f:
    data = json.load(f)

normas = {n['id_norma']: n for n in data['normas']}

print("\n📋 PASO 1: Detección de temas por KEYWORDS")
print("="*80)

keywords_map = {
    'POTENCIA': ['potencia', 'suficiencia'],
    'TRANSFERENCIAS': ['transferencia', 'pago', 'compensación'],
    'GENERACION': ['generador', 'generadora', 'central'],
    'SSCC': ['servicios complementarios', 'sscc', 'regulación'],
}

print("\nEjemplo de keywords usadas:")
for tema, keywords in keywords_map.items():
    print(f"  {tema:15} → {', '.join(keywords[:3])}")

print("\n⚠️  LIMITACIÓN:")
print("   - Puede dar FALSOS POSITIVOS (ej: 'potencia' en Código Penal)")
print("   - Puede dar FALSOS NEGATIVOS (ej: norma relevante sin keyword)")
print("   - Solo busca en TÍTULO y HTML, NO en texto completo")

# Probar con un caso
caso = "central mejoró su suficiencia"
caso_lower = caso.lower()

temas_detectados = set()
for tema, keywords in keywords_map.items():
    for keyword in keywords:
        if keyword in caso_lower:
            temas_detectados.add(tema)
            print(f"\n   ✓ Detectado '{keyword}' → Tema: {tema}")

print(f"\n📊 PASO 2: Matching con normas")
print("="*80)

# Contar normas por tema
for tema in temas_detectados:
    normas_tema = [n for n in normas.values() if tema in n.get('temas_detectados', [])]
    print(f"\n{tema}:")
    print(f"  {len(normas_tema)} normas encontradas")

    # Mostrar posibles falsos positivos
    generales = [n for n in normas_tema[:20] if 'CODIGO' in n.get('titulo', '').upper() or 'GENERAL' in n.get('titulo', '').upper()]
    if generales:
        print(f"  ⚠️  Posibles falsos positivos: {len(generales)}")
        for n in generales[:3]:
            print(f"     - {n['tipo']} {n['numero']} - {n['titulo'][:60]}")

print(f"\n🎯 PASO 3: Ordenamiento por RELEVANCIA")
print("="*80)

# Construir grafo de referencias
grafo_refs = {}
for n in normas.values():
    for vinc in n.get('vinculaciones_ids', []):
        if vinc not in grafo_refs:
            grafo_refs[vinc] = []
        grafo_refs[vinc].append(n['id_norma'])

print("\nCriterio: Número de veces que una norma es citada por otras")
print("\nEjemplo - Top 5 normas más citadas:")

normas_ordenadas = sorted(normas.values(), key=lambda n: len(grafo_refs.get(n['id_norma'], [])), reverse=True)[:5]

for i, norma in enumerate(normas_ordenadas, 1):
    refs = len(grafo_refs.get(norma['id_norma'], []))
    print(f"{i}. {norma['tipo']} {norma['numero']:>6} - {refs:2} referencias")
    print(f"   {norma['titulo'][:65]}")

print("\n⚠️  LIMITACIÓN:")
print("   - Norma muy citada puede NO ser relevante al caso específico")
print("   - Norma poco citada puede SER muy relevante técnicamente")

print(f"\n🔬 PASO 4: Identificación de normas técnicas específicas")
print("="*80)

print("\nSe identifican normas clave manualmente:")
print("  • D.62 - Transferencias de Potencia")
print("  • D.113 - Servicios Complementarios")
print("  • DFL 4 - Ley General de Servicios Eléctricos")

print("\n✓ VENTAJA: Alta precisión para normas conocidas")
print("⚠️  LIMITACIÓN: Solo funciona con normas pre-identificadas")

print(f"\n📈 CONFIABILIDAD DEL SISTEMA")
print("="*80)

# Calcular estadísticas
total_normas = len(normas)
con_temas = sum(1 for n in normas.values() if n.get('temas_detectados'))
sin_temas = total_normas - con_temas

print(f"\nCobertura de detección de temas:")
print(f"  Normas CON temas detectados: {con_temas:,} ({con_temas/total_normas*100:.1f}%)")
print(f"  Normas SIN temas:            {sin_temas:,} ({sin_temas/total_normas*100:.1f}%)")

# Temas detectados
from collections import Counter
todos_temas = []
for n in normas.values():
    todos_temas.extend(n.get('temas_detectados', []))

temas_count = Counter(todos_temas)

print(f"\nDistribución de temas:")
for tema, count in temas_count.most_common(5):
    print(f"  {tema:15} {count:4} normas")

print(f"\n⚠️  FALSOS POSITIVOS estimados:")
# Estimar normas generales mal clasificadas
generales_mal = 0
for n in normas.values():
    titulo = n.get('titulo', '').upper()
    if any(x in titulo for x in ['CODIGO', 'ORGÁNICO', 'CONSTITUCIÓN', 'PENAL']):
        if n.get('temas_detectados'):
            generales_mal += 1

print(f"  ~{generales_mal} normas generales con temas eléctricos")
print(f"  ({generales_mal/con_temas*100:.1f}% del total con temas)")

print(f"\n{'='*80}")
print("💡 CONCLUSIÓN")
print("="*80)

print("""
ESTE SISTEMA ES:
✓ Bueno para: PRIMERA APROXIMACIÓN y mapeo general
✓ Bueno para: Identificar normas clave conocidas (D.62, D.113, etc.)
✓ Bueno para: Visualizar red de relaciones entre normas

⚠️  LIMITADO para:
✗ Análisis detallado de artículos específicos (no tenemos texto completo)
✗ Interpretar contenido legal (necesita abogado)
✗ Casos muy específicos o novedosos
✗ Determinar aplicabilidad exacta sin leer la norma

RECOMENDACIÓN:
1. Usar este sistema para identificar normas candidatas
2. LEER el texto completo en BCN de las normas identificadas
3. CONSULTAR con abogado especializado para interpretación legal
4. VERIFICAR versiones vigentes y modificaciones

COSTO:
- Esta herramienta: GRATIS (automatizada)
- Leer normas en BCN: GRATIS
- Asesoría legal especializada: $$ (necesaria para casos reales)
""")

print("="*80)
