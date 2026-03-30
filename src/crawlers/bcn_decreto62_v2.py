#!/usr/bin/env python3
"""Buscar Decreto 62 - Reglamento Transferencias de Potencia (2006)."""

import asyncio
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Búsqueda más específica
        searches = [
            "Reglamento transferencias potencia empresas generadoras",
            "decreto 62 2006 energía",
            "transferencias de potencia ley general servicios eléctricos",
        ]

        for search in searches:
            print(f"\n{'='*60}")
            print(f"Buscando: {search}")
            url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(search)}"

            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)

            # Ver texto de la página
            text = await page.evaluate('''() => {
                return document.body ? document.body.innerText : '';
            }''')

            # Buscar menciones relevantes
            lines = text.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                if any(kw in line.lower() for kw in ['decreto', 'transferencia', 'potencia', '62']):
                    if len(line) > 10:
                        print(f"  {line[:100]}")

            # Buscar links
            links = await page.evaluate('''() => {
                const links = document.querySelectorAll('a[href*="navegar?idNorma"]');
                return Array.from(links).slice(0, 3).map(l => ({
                    text: l.innerText.trim().substring(0, 100),
                    href: l.href
                }));
            }''')

            if links:
                print("\n  Links encontrados:")
                for l in links:
                    print(f"    - {l['text']}")
                    print(f"      {l['href']}")

        # Probar URL directa conocida del Decreto 62 de Economía 2006
        # idNorma conocido: 251718 (Decreto 62 de 2006 Ministerio de Economía)
        direct_url = "https://www.bcn.cl/leychile/navegar?idNorma=251718"
        print(f"\n{'='*60}")
        print(f"Probando URL directa: {direct_url}")

        await page.goto(direct_url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        content = await page.evaluate('''() => {
            return document.body ? document.body.innerText : '';
        }''')

        print("\n" + "=" * 70)
        print("CONTENIDO:")
        print("=" * 70)
        print(content[:15000])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
