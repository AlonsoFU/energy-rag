#!/usr/bin/env python3
"""
Test de velocidad y calidad de descarga.

Compara tiempo real de descarga y valida calidad del contenido.
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.norm_detail_crawler_OPTIMIZED import NormDetailCrawlerOptimized


async def test_single_norm(id_norma: str, nombre: str):
    """Probar descarga de una sola norma."""
    print(f"\n{'='*70}")
    print(f"📥 Descargando: {nombre} (ID: {id_norma})")
    print(f"{'='*70}")

    start = time.time()

    async with NormDetailCrawlerOptimized(headless=True, validate=True) as crawler:
        result = await crawler.fetch_norm(id_norma)

    elapsed = time.time() - start

    if not result:
        print(f"\n❌ FALLO en {elapsed:.2f}s")
        return None

    # Mostrar resultados
    print(f"\n✅ ÉXITO en {elapsed:.2f}s")
    print(f"\n📊 Metadatos:")
    print(f"  Tipo: {result.tipo} {result.numero}")
    print(f"  Título: {result.titulo[:80]}...")
    print(f"  Organismo: {result.organismo}")
    print(f"  Fecha publicación: {result.fecha_publicacion}")

    print(f"\n📄 Texto completo:")
    print(f"  Longitud: {len(result.texto_completo):,} caracteres")
    print(f"  Palabras: ~{len(result.texto_completo.split()):,}")

    # Validación
    val = result.validation_status
    print(f"\n🔍 Validación:")
    print(f"  Status: {val['status']}")
    print(f"  Artículos detectados: {val.get('num_articulos', 0)}")

    if val.get('issues'):
        print(f"  ⚠️  Issues: {', '.join(val['issues'])}")
    if val.get('warnings'):
        print(f"  ⚠️  Warnings: {', '.join(val['warnings'])}")

    # Muestra de texto
    print(f"\n📝 Muestra del texto (primeros 500 chars):")
    print("-" * 70)
    print(result.texto_completo[:500])
    print("-" * 70)

    # Buscar artículos
    import re
    articulos = re.findall(r'Artículo\s+\d+[º°o]?', result.texto_completo[:2000])
    if articulos:
        print(f"\n📑 Artículos encontrados (muestra): {', '.join(articulos[:5])}")

    return elapsed


async def test_multiple_norms():
    """Probar con varias normas para calcular promedio."""
    normas_test = [
        ('250604', 'Decreto 62 - Transferencias de Potencia'),
        ('258171', 'DFL 4 - Ley General Servicios Eléctricos'),
        ('252841', 'Decreto 44 - Modifica D.62'),
        ('1032928', 'Ley 20.936 - Transmisión'),
        ('1074277', 'Ley 20.805'),
    ]

    print("\n" + "="*70)
    print("🔬 TEST DE VELOCIDAD Y CALIDAD")
    print("="*70)
    print(f"\nProbando {len(normas_test)} normas para calcular tiempo promedio...")

    times = []
    successful = 0

    for id_norma, nombre in normas_test:
        elapsed = await test_single_norm(id_norma, nombre)

        if elapsed:
            times.append(elapsed)
            successful += 1

        # Pequeño delay entre pruebas
        await asyncio.sleep(2)

    # Resumen
    print("\n" + "="*70)
    print("📊 RESUMEN DE PRUEBAS")
    print("="*70)

    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        print(f"\n⏱️  Tiempos:")
        print(f"  Promedio: {avg_time:.2f}s por norma")
        print(f"  Mínimo: {min_time:.2f}s")
        print(f"  Máximo: {max_time:.2f}s")

        print(f"\n✅ Éxito: {successful}/{len(normas_test)}")

        # Estimaciones
        print(f"\n📈 ESTIMACIONES PARA 2,031 NORMAS:")
        print(f"  Solo descarga: {(avg_time * 2031) / 3600:.1f} horas")

        delays = [5, 10, 15, 20, 30]
        print(f"\n  Con diferentes delays anti-bloqueo:")
        for delay in delays:
            total_hours = (avg_time * 2031 + delay * 2031) / 3600
            print(f"    {delay}s delay → {total_hours:.1f} horas total")

        print(f"\n💡 RECOMENDACIÓN:")
        if avg_time < 5:
            print(f"  ✅ Descarga rápida (~{avg_time:.1f}s)")
            print(f"  ✅ Delay de 10-15s es suficiente")
            print(f"  ✅ Tiempo total: ~8-12 horas")
        elif avg_time < 10:
            print(f"  ⚠️  Descarga moderada (~{avg_time:.1f}s)")
            print(f"  ⚠️  Delay de 15-20s recomendado")
            print(f"  ⚠️  Tiempo total: ~12-18 horas")
        else:
            print(f"  ❌ Descarga lenta (~{avg_time:.1f}s)")
            print(f"  ❌ Revisar optimizaciones")

    else:
        print("\n❌ No se pudo descargar ninguna norma")


async def test_validation():
    """Probar validación de calidad."""
    print("\n" + "="*70)
    print("🔍 TEST DE VALIDACIÓN DE CALIDAD")
    print("="*70)

    # Probar con una norma válida
    print("\n1️⃣  Norma válida (Decreto 62):")
    async with NormDetailCrawlerOptimized(headless=True, validate=True) as crawler:
        result = await crawler.fetch_norm('250604')

        if result:
            val = result.validation_status
            print(f"  Status: {val['status']}")
            print(f"  Longitud: {val['text_length']} chars")
            print(f"  Artículos: {val.get('num_articulos', 0)}")
            print(f"  Palabras: {val.get('num_palabras', 0)}")

            if val['status'] == 'VALID':
                print(f"  ✅ Validación pasada")
            else:
                print(f"  ⚠️  Issues: {val.get('issues', [])}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Test de velocidad y calidad de descarga')
    parser.add_argument('--single', help='Probar una sola norma (ID)')
    parser.add_argument('--multiple', action='store_true',
                       help='Probar varias normas para calcular promedio')
    parser.add_argument('--validation', action='store_true',
                       help='Probar validación de calidad')

    args = parser.parse_args()

    if args.single:
        asyncio.run(test_single_norm(args.single, f"Norma {args.single}"))
    elif args.validation:
        asyncio.run(test_validation())
    else:
        # Por defecto: test múltiple
        asyncio.run(test_multiple_norms())
