#!/usr/bin/env python3
"""
BCN - Búsqueda directa de normas 2025.
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def extract_visible_norms(page):
    """Extrae normas visibles de la página actual."""
    return await page.evaluate('''() => {
        const results = [];
        const seen = new Set();

        // Buscar en el texto completo de la página
        const text = document.body.innerText;
        const lines = text.split('\\n');

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // Detectar fecha 2025
            const dateMatch = line.match(/(\\d{2}-[A-Z]{3}-2025)/i);
            if (dateMatch) {
                // Buscar siguiente línea que tenga tipo de norma
                for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
                    const nextLine = lines[j].trim();
                    if (nextLine.match(/^(LEY|DECRETO|DFL|RESOLUCIÓN)/i)) {
                        const key = dateMatch[1] + nextLine.substring(0, 50);
                        if (!seen.has(key)) {
                            seen.add(key);
                            results.push({
                                fecha: dateMatch[1],
                                norma: nextLine.substring(0, 200),
                                contexto: lines.slice(i, i+4).join(' ').substring(0, 300)
                            });
                        }
                        break;
                    }
                }
            }
        }

        return results;
    }''')


async def main():
    print("=" * 60)
    print("BCN - Búsqueda directa de normas 2025")
    print("=" * 60)

    searches = [
        ("energía 2025", "Energía general"),
        ("eléctrico 2025", "Eléctrico"),
        ("decreto 2025 energía", "Decretos energía"),
        ("resolución 2025 energía", "Resoluciones energía"),
        ("ley 2025 energía", "Leyes energía"),
        ("Ministerio Energía 2025", "Ministerio"),
    ]

    all_results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for search_term, label in searches:
            print(f"\n{label}: '{search_term}'")
            print("-" * 40)

            from urllib.parse import quote
            url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(search_term)}"

            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Extraer normas 2025 visibles
            normas = await extract_visible_norms(page)

            print(f"  Normas 2025 encontradas: {len(normas)}")

            for n in normas[:5]:
                print(f"    [{n['fecha']}] {n['norma'][:50]}...")

            all_results[label] = normas

        await browser.close()

    # Consolidar y deduplicar
    todas = []
    seen = set()
    for label, normas in all_results.items():
        for n in normas:
            key = n['fecha'] + n['norma'][:30]
            if key not in seen:
                seen.add(key)
                n['busqueda'] = label
                todas.append(n)

    # Guardar
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_energia_2025_directo.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(todas, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("RESUMEN FINAL")
    print("=" * 60)
    print(f"\nTotal normas únicas 2025: {len(todas)}")

    if todas:
        print("\nDetalle:")
        for n in todas:
            print(f"  [{n['fecha']}] {n['norma'][:60]}...")

    print(f"\nGuardado: {output}")

    return todas


if __name__ == "__main__":
    asyncio.run(main())
