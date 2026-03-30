#!/usr/bin/env python3
"""
BCN - Explorar índice de materias/temas.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def main():
    print("=" * 60)
    print("BCN - ÍNDICE DE MATERIAS/TEMAS")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Ir a "Leyes por temas"
        print("\n1. Explorando 'Leyes por temas'...")
        await page.goto(
            "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2",
            wait_until='networkidle',
            timeout=30000
        )
        await asyncio.sleep(3)

        # Extraer categorías
        categorias = await page.evaluate('''() => {
            const cats = [];

            // Buscar todos los enlaces con parámetros de categoría
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                const text = a.textContent.trim();

                // Buscar enlaces con sub= o agr=
                if ((href.includes('sub=') || href.includes('agr=')) && text.length > 2) {
                    // Extraer parámetros
                    const subMatch = href.match(/sub=(\\d+)/);
                    const agrMatch = href.match(/agr=(\\d+)/);

                    cats.push({
                        nombre: text.substring(0, 100),
                        url: href,
                        sub: subMatch ? subMatch[1] : null,
                        agr: agrMatch ? agrMatch[1] : null
                    });
                }
            });

            return cats;
        }''')

        print(f"\n  Categorías encontradas: {len(categorias)}")

        # Mostrar categorías únicas
        seen = set()
        unique_cats = []
        for cat in categorias:
            key = cat['sub'] or cat['agr']
            if key and key not in seen:
                seen.add(key)
                unique_cats.append(cat)

        print(f"  Categorías únicas: {len(unique_cats)}")
        print("\n  Lista de materias:")
        for cat in unique_cats[:30]:
            print(f"    [{cat.get('agr', '')}/{cat.get('sub', '')}] {cat['nombre']}")

        # Buscar categorías de ENERGÍA
        print("\n" + "-" * 40)
        print("  CATEGORÍAS RELACIONADAS CON ENERGÍA:")
        print("-" * 40)

        energy_cats = []
        keywords = ['energía', 'eléctric', 'electricidad', 'combustible', 'gas', 'petróleo', 'minería']
        for cat in unique_cats:
            nombre_lower = cat['nombre'].lower()
            if any(kw in nombre_lower for kw in keywords):
                energy_cats.append(cat)
                print(f"    ✓ [{cat.get('sub', '')}] {cat['nombre']}")

        # Explorar una categoría de energía si existe
        if energy_cats:
            print("\n" + "=" * 60)
            print("2. Explorando categoría de energía...")
            print("=" * 60)

            cat = energy_cats[0]
            await page.goto(cat['url'], wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Extraer normas de esta categoría
            normas = await page.evaluate('''() => {
                const results = [];
                const text = document.body.innerText;
                const lines = text.split('\\n');

                for (let i = 0; i < lines.length; i++) {
                    const line = lines[i].trim();
                    // Buscar fechas
                    const dateMatch = line.match(/^(\\d{2}-[A-Z]{3}-\\d{4})$/i);
                    if (dateMatch) {
                        // Siguiente línea es el tipo de norma
                        if (i + 1 < lines.length) {
                            results.push({
                                fecha: dateMatch[1],
                                norma: lines[i + 1].trim().substring(0, 150)
                            });
                        }
                    }
                }
                return results;
            }''')

            print(f"\n  Normas en categoría '{cat['nombre']}':")
            print(f"  Total: {len(normas)}")
            for n in normas[:10]:
                print(f"    [{n['fecha']}] {n['norma'][:50]}...")

        # Guardar todas las categorías
        DATA_RAW.mkdir(parents=True, exist_ok=True)
        output = DATA_RAW / "bcn_materias.json"
        with open(output, 'w', encoding='utf-8') as f:
            json.dump({
                'todas': unique_cats,
                'energia': energy_cats
            }, f, indent=2, ensure_ascii=False)

        print(f"\n\nGuardado: {output}")

        # También mostrar el texto visible para entender la estructura
        body_text = await page.inner_text('body')
        print("\n" + "=" * 60)
        print("TEXTO DE LA PÁGINA DE MATERIAS:")
        print("=" * 60)
        print(body_text[:2500])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
