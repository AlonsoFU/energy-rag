#!/usr/bin/env python3
"""
BCN - Explorar categorías de ENERGÍA en detalle.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def extract_normas_from_category(page, url, name):
    """Extrae todas las normas de una categoría."""
    print(f"\n  Explorando: {name}")
    print(f"  URL: {url}")

    await page.goto(url, wait_until='networkidle', timeout=30000)
    await asyncio.sleep(3)

    # Extraer normas
    normas = await page.evaluate('''() => {
        const results = [];
        const text = document.body.innerText;

        // Buscar patrones de norma
        const lines = text.split('\\n');
        let current = null;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // Fecha
            const dateMatch = line.match(/^(\\d{2}-[A-Z]{3}-\\d{4})$/i);
            if (dateMatch) {
                if (current) results.push(current);
                current = {fecha: dateMatch[1], tipo: '', titulo: ''};
                continue;
            }

            // Tipo de norma (después de fecha)
            if (current && !current.tipo) {
                const tipoMatch = line.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN|AUTO)/i);
                if (tipoMatch) {
                    current.tipo = line.substring(0, 100);
                    continue;
                }
            }

            // Título (después de tipo)
            if (current && current.tipo && !current.titulo && line.length > 10) {
                current.titulo = line.substring(0, 200);
            }
        }

        if (current) results.push(current);
        return results;
    }''')

    print(f"  Normas: {len(normas)}")
    return normas


async def main():
    print("=" * 60)
    print("BCN - CATEGORÍAS DE ENERGÍA")
    print("=" * 60)

    # Categorías de energía encontradas
    energy_categories = [
        {
            "nombre": "ENERGIA (General)",
            "url": "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&comp=&sub=704",
            "sub": "704"
        },
        {
            "nombre": "Energía Nuclear",
            "url": "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&comp=&sub=1138",
            "sub": "1138"
        },
        {
            "nombre": "Energía Renovable",
            "url": "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&comp=&sub=1139",
            "sub": "1139"
        },
        {
            "nombre": "Institucionalidad Energética",
            "url": "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&comp=&sub=1140",
            "sub": "1140"
        },
        {
            "nombre": "Gas",
            "url": "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&comp=&sub=1197",
            "sub": "1197"
        },
        {
            "nombre": "Impuesto Combustibles",
            "url": "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&comp=&sub=1168",
            "sub": "1168"
        },
    ]

    all_results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Primero, explorar la página principal de temas para encontrar más categorías
        print("\n" + "=" * 60)
        print("1. Buscando TODAS las categorías de energía")
        print("=" * 60)

        await page.goto(
            "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2",
            wait_until='networkidle',
            timeout=30000
        )
        await asyncio.sleep(3)

        # Buscar todas las categorías relacionadas con energía
        all_cats = await page.evaluate('''() => {
            const cats = [];
            const text = document.body.innerText.toLowerCase();

            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const aText = a.textContent.trim();
                const aTextLower = aText.toLowerCase();

                if (href.includes('sub=')) {
                    const subMatch = href.match(/sub=(\\d+)/);
                    if (subMatch) {
                        // Categorías de energía/electricidad
                        const keywords = ['energía', 'energa', 'eléctric', 'electric',
                                         'combustible', 'gas', 'petróleo', 'minería',
                                         'servicios públicos'];
                        if (keywords.some(k => aTextLower.includes(k))) {
                            cats.push({
                                nombre: aText.substring(0, 80),
                                sub: subMatch[1],
                                url: href
                            });
                        }
                    }
                }
            });

            return cats;
        }''')

        print(f"\n  Categorías de energía encontradas: {len(all_cats)}")
        for cat in all_cats:
            print(f"    [{cat['sub']}] {cat['nombre']}")

        # Explorar cada categoría
        print("\n" + "=" * 60)
        print("2. Explorando cada categoría")
        print("=" * 60)

        # Usar las categorías encontradas o las predefinidas
        cats_to_explore = all_cats if all_cats else energy_categories

        for cat in cats_to_explore[:10]:
            normas = await extract_normas_from_category(page, cat['url'], cat['nombre'])
            all_results[cat['nombre']] = {
                'sub': cat.get('sub'),
                'url': cat['url'],
                'total': len(normas),
                'normas': normas
            }

            # Filtrar 2025
            normas_2025 = [n for n in normas if '2025' in n.get('fecha', '')]
            if normas_2025:
                print(f"    → 2025: {len(normas_2025)} normas")
                for n in normas_2025[:3]:
                    print(f"      [{n['fecha']}] {n.get('tipo', '')[:30]}...")

            await asyncio.sleep(1)

        await browser.close()

    # Guardar resultados
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_categorias_energia.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    total_normas = 0
    total_2025 = 0

    for cat_name, data in all_results.items():
        normas_2025 = [n for n in data['normas'] if '2025' in n.get('fecha', '')]
        total_normas += data['total']
        total_2025 += len(normas_2025)
        print(f"\n  {cat_name}:")
        print(f"    Total: {data['total']}, 2025: {len(normas_2025)}")

    print(f"\n  TOTAL GENERAL: {total_normas} normas, {total_2025} de 2025")
    print(f"\n  Guardado: {output}")


if __name__ == "__main__":
    asyncio.run(main())
