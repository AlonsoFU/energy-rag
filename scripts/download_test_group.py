#!/usr/bin/env python3
"""
Descargar las 10 normas del grupo de prueba.
Busca IDs faltantes y descarga contenido completo.
"""

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from src.crawlers.norm_detail_crawler import NormDetailCrawler, NormData


async def search_norm_id(page, busqueda: str) -> str:
    """
    Buscar una norma en BCN y obtener su id_norma.

    Args:
        page: Página de Playwright
        busqueda: Términos de búsqueda

    Returns:
        id_norma o None
    """
    url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(busqueda)}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        # Buscar primer resultado con idNorma
        result = await page.evaluate('''() => {
            const links = document.querySelectorAll('a[href*="idNorma"]');
            for (const link of links) {
                const match = link.href.match(/idNorma=(\\d+)/);
                if (match) {
                    return {
                        id_norma: match[1],
                        titulo: link.innerText.trim().substring(0, 100)
                    };
                }
            }
            return null;
        }''')

        if result:
            return result['id_norma']

    except Exception as e:
        print(f"    Error buscando: {e}")

    return None


async def main():
    print("=" * 70)
    print("DESCARGA DE GRUPO DE PRUEBA - 10 NORMAS BCN")
    print("=" * 70)

    # Cargar grupo de prueba
    test_group_path = Path(__file__).parent.parent / "data" / "test_group.json"
    with open(test_group_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    normas = data['normas']
    print(f"\nNormas a descargar: {len(normas)}")

    # Estadísticas
    stats = {
        'total': len(normas),
        'ids_conocidos': sum(1 for n in normas if n.get('id_norma')),
        'ids_buscados': 0,
        'descargadas': 0,
        'errores': 0
    }

    print(f"IDs conocidos: {stats['ids_conocidos']}")
    print(f"IDs a buscar: {stats['total'] - stats['ids_conocidos']}")

    # Iniciar browser
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    stealth = Stealth()
    await stealth.apply_stealth_async(context)
    search_page = await context.new_page()

    # Paso 1: Buscar IDs faltantes
    print("\n" + "-" * 70)
    print("PASO 1: Buscar IDs faltantes")
    print("-" * 70)

    for norma in normas:
        if not norma.get('id_norma'):
            print(f"\n  Buscando: {norma['nombre']}...")
            id_norma = await search_norm_id(search_page, norma['busqueda'])
            if id_norma:
                norma['id_norma'] = id_norma
                stats['ids_buscados'] += 1
                print(f"    Encontrado: {id_norma}")
            else:
                print(f"    NO ENCONTRADO")

    await search_page.close()

    # Guardar IDs actualizados
    with open(test_group_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n  IDs guardados en: {test_group_path}")

    # Paso 2: Descargar normas
    print("\n" + "-" * 70)
    print("PASO 2: Descargar contenido completo")
    print("-" * 70)

    crawler = NormDetailCrawler(headless=True)
    crawler.playwright = playwright
    crawler.browser = browser
    crawler.context = context

    resultados = []

    for i, norma in enumerate(normas, 1):
        id_norma = norma.get('id_norma')
        print(f"\n[{i}/{len(normas)}] {norma['nombre']}")

        if not id_norma:
            print(f"  SKIP: Sin id_norma")
            stats['errores'] += 1
            continue

        try:
            norm_data = await crawler.fetch_norm(id_norma)
            if norm_data:
                paths = crawler.save_norm(norm_data)
                stats['descargadas'] += 1
                resultados.append({
                    'nombre': norma['nombre'],
                    'id_norma': id_norma,
                    'titulo': norm_data.titulo[:80],
                    'caracteres': len(norm_data.texto_completo),
                    'json': paths['json'],
                    'txt': paths['txt']
                })
                print(f"  OK: {len(norm_data.texto_completo)} caracteres")
            else:
                stats['errores'] += 1
                print(f"  ERROR: No se pudo descargar")

        except Exception as e:
            stats['errores'] += 1
            print(f"  ERROR: {e}")

        # Pequeña pausa entre descargas
        await asyncio.sleep(1)

    await browser.close()
    await playwright.stop()

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"\nTotal normas: {stats['total']}")
    print(f"IDs conocidos: {stats['ids_conocidos']}")
    print(f"IDs buscados: {stats['ids_buscados']}")
    print(f"Descargadas: {stats['descargadas']}")
    print(f"Errores: {stats['errores']}")

    print(f"\nArchivos creados:")
    for r in resultados:
        print(f"  {r['nombre']}: {r['caracteres']} chars")
        print(f"    JSON: {r['json']}")

    # Verificar criterios de éxito
    print("\n" + "-" * 70)
    print("VERIFICACION")
    print("-" * 70)
    success = stats['descargadas'] >= 8  # Al menos 8 de 10
    print(f"  Descargadas >= 8: {'OK' if success else 'FAIL'} ({stats['descargadas']}/10)")

    # Guardar resumen
    summary_path = Path(__file__).parent.parent / "data" / "test_group_results.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump({
            'stats': stats,
            'resultados': resultados
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Resumen guardado: {summary_path}")

    return stats['descargadas']


if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result >= 8 else 1)
