#!/usr/bin/env python3
"""
BCN - Búsqueda avanzada con filtros de fecha.
Explora cómo BCN estructura sus búsquedas.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def explore_bcn_search(page):
    """Explora la búsqueda avanzada de BCN."""

    print("\n" + "=" * 60)
    print("1. Explorando búsqueda avanzada de BCN")
    print("=" * 60)

    # Ir a búsqueda avanzada
    await page.goto(
        "https://www.bcn.cl/leychile/consulta/busqueda_avanzada",
        wait_until='networkidle',
        timeout=30000
    )
    await asyncio.sleep(3)

    # Ver qué filtros hay disponibles
    content = await page.content()
    print(f"   Contenido: {len(content)} chars")

    # Buscar selectores de fecha
    selects = await page.query_selector_all('select')
    print(f"   Selectores encontrados: {len(selects)}")

    inputs = await page.query_selector_all('input')
    print(f"   Inputs encontrados: {len(inputs)}")

    # Mostrar texto de la página
    body = await page.inner_text('body')
    print("\n   Texto de búsqueda avanzada (primeros 1000 chars):")
    print(body[:1000])

    return body


async def search_by_organism_2025(page):
    """Busca por organismo Ministerio de Energía."""

    print("\n" + "=" * 60)
    print("2. Buscando 'Ministerio de Energía' - todas las páginas")
    print("=" * 60)

    await page.goto(
        "https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena=Ministerio%20de%20Energ%C3%ADa",
        wait_until='networkidle',
        timeout=30000
    )
    await asyncio.sleep(3)

    # Contar total de resultados
    body = await page.inner_text('body')

    # Buscar el contador de resultados
    import re
    total_match = re.search(r'de\s+([\d.,]+)\s*$', body[:500], re.MULTILINE)
    if total_match:
        print(f"   Total resultados: {total_match.group(1)}")

    # Extraer TODAS las normas visibles y sus fechas
    normas = await page.evaluate('''() => {
        const results = [];

        // Buscar filas de resultados
        const rows = document.querySelectorAll('tr, .resultado, li');

        rows.forEach(row => {
            const text = row.innerText || '';
            const links = row.querySelectorAll('a[href*="idNorma"]');

            links.forEach(a => {
                const href = a.href;
                const match = href.match(/idNorma=(\\d+)/);
                if (match) {
                    // Buscar fecha en formato DD-MMM-YYYY
                    const dateMatch = text.match(/(\\d{2}-[A-Z]{3}-\\d{4})/i);
                    results.push({
                        id: match[1],
                        titulo: a.textContent.trim().substring(0, 150),
                        fecha: dateMatch ? dateMatch[1] : '',
                        texto: text.substring(0, 200)
                    });
                }
            });
        });

        return results;
    }''')

    print(f"   Normas en página: {len(normas)}")

    # Filtrar por 2025
    normas_2025 = [n for n in normas if '2025' in n.get('fecha', '')]
    print(f"   Normas 2025: {len(normas_2025)}")

    for n in normas_2025[:10]:
        print(f"     [{n['fecha']}] {n['titulo'][:50]}...")

    return normas, normas_2025


async def search_recent_energy(page):
    """Busca normas recientes del Ministerio de Energía."""

    print("\n" + "=" * 60)
    print("3. Explorando página del Ministerio de Energía")
    print("=" * 60)

    # Buscar por organismo específico
    await page.goto(
        "https://www.bcn.cl/leychile/Consulta/listado_n_702?agr=1160&sub=912",
        wait_until='networkidle',
        timeout=30000
    )
    await asyncio.sleep(3)

    body = await page.inner_text('body')
    print(f"   Contenido: {len(body)} chars")
    print("\n   Primeros 800 chars:")
    print(body[:800])

    # Extraer normas
    normas = await page.evaluate('''() => {
        const results = [];
        document.querySelectorAll('a[href*="idNorma"]').forEach(a => {
            const match = a.href.match(/idNorma=(\\d+)/);
            if (match) {
                const parent = a.closest('tr') || a.parentElement;
                const text = parent ? parent.innerText : '';
                const dateMatch = text.match(/(\\d{2}-[A-Z]{3}-\\d{4})/i);
                results.push({
                    id: match[1],
                    titulo: a.textContent.trim().substring(0, 100),
                    fecha: dateMatch ? dateMatch[1] : '',
                    contexto: text.substring(0, 150)
                });
            }
        });
        return results;
    }''')

    print(f"\n   Normas encontradas: {len(normas)}")

    # Mostrar las primeras
    for n in normas[:15]:
        print(f"     [{n['fecha']}] {n['titulo'][:50]}...")

    return normas


async def main():
    print("=" * 60)
    print("BCN - Exploración de búsqueda avanzada")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        # Explorar búsqueda avanzada
        await explore_bcn_search(page)

        # Buscar por Ministerio de Energía
        todas, normas_2025 = await search_by_organism_2025(page)

        # Explorar categoría específica
        await search_recent_energy(page)

        await browser.close()

    # Guardar resultados
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    output = DATA_RAW / "bcn_exploracion.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump({
            'ministerio_energia': todas,
            'ministerio_energia_2025': normas_2025
        }, f, indent=2, ensure_ascii=False)

    print(f"\n\nGuardado en: {output}")


if __name__ == "__main__":
    asyncio.run(main())
