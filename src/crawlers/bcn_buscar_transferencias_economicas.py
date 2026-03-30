#!/usr/bin/env python3
"""Buscar transferencias económicas en BCN."""

import asyncio
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def search_bcn(page, term: str) -> list:
    url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(term)}"
    print(f"\nBuscando: '{term}'")

    await page.goto(url, wait_until='networkidle', timeout=30000)
    await asyncio.sleep(2)

    normas = await page.evaluate('''() => {
        const results = [];
        if (!document.body) return results;

        const text = document.body.innerText || '';
        const lines = text.split('\\n');

        let current = null;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            const dateMatch = line.match(/^(\\d{2})-([A-Z]{3})-(\\d{4})$/i);
            if (dateMatch) {
                if (current && current.tipo) {
                    results.push(current);
                }
                current = {
                    fecha: line,
                    año: parseInt(dateMatch[3]),
                    tipo: '',
                    titulo: '',
                    organismo: ''
                };
                continue;
            }

            if (current) {
                if (!current.tipo) {
                    const tipoMatch = line.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN|AUTO)/i);
                    if (tipoMatch) {
                        current.tipo = line.substring(0, 150);
                        continue;
                    }
                }

                if (current.tipo && !current.titulo && line.length > 15 &&
                    !line.match(/^MINISTERIO|^Alertas|^Vinculaciones/i)) {
                    current.titulo = line.substring(0, 300);
                }

                if (line.match(/^MINISTERIO|^COMISIÓN/i)) {
                    current.organismo = line.substring(0, 150);
                }
            }
        }

        if (current && current.tipo) {
            results.push(current);
        }

        return results;
    }''')

    print(f"  Encontradas: {len(normas)}")
    return normas

async def main():
    print("=" * 60)
    print("BCN - Búsqueda de Transferencias Económicas")
    print("=" * 60)

    searches = [
        "transferencias económicas electricidad",
        "transferencias económicas energía",
        "transferencias económicas sistema eléctrico",
        "balance económico eléctrico",
        "valorización transferencias electricidad",
        "pagos entre generadoras",
        "liquidación transferencias eléctricas",
    ]

    all_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for term in searches:
            normas = await search_bcn(page, term)

            for n in normas:
                key = f"{n['fecha']}_{n.get('tipo', '')[:30]}"
                if key not in all_normas:
                    n['busqueda'] = term
                    all_normas[key] = n

            await asyncio.sleep(1)

        await browser.close()

    print("\n" + "=" * 60)
    print("RESULTADOS")
    print("=" * 60)
    print(f"\nTotal normas únicas: {len(all_normas)}")

    for n in list(all_normas.values())[:20]:
        print(f"\n[{n['fecha']}] {n['tipo']}")
        if n['titulo']:
            print(f"  {n['titulo'][:80]}")
        print(f"  Búsqueda: {n['busqueda']}")

if __name__ == "__main__":
    asyncio.run(main())
