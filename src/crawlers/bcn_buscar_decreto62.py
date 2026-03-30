#!/usr/bin/env python3
"""Buscar y extraer Decreto 62 de Transferencias de Potencia."""

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

        # Buscar Decreto 62 Transferencias de Potencia
        search = "Decreto 62 transferencias potencia generadoras"
        url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(search)}"

        print(f"Buscando: {search}")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        # Obtener primer resultado y su link
        result = await page.evaluate('''() => {
            const links = document.querySelectorAll('a[href*="navegar?idNorma"]');
            const results = [];
            for (const link of links) {
                results.push({
                    text: link.innerText.trim(),
                    href: link.href
                });
            }
            return results.slice(0, 5);
        }''')

        print("\nResultados encontrados:")
        for r in result:
            print(f"  - {r['text'][:80]}")
            print(f"    URL: {r['href']}")

        # Si encontramos el decreto, ir a él
        if result:
            # Buscar el que tenga "62" y "potencia" o "generadora"
            target = None
            for r in result:
                if "62" in r['text'] and ("potencia" in r['text'].lower() or "generadora" in r['text'].lower()):
                    target = r['href']
                    break

            if not target and result:
                target = result[0]['href']

            if target:
                print(f"\nAccediendo a: {target}")
                await page.goto(target, wait_until='networkidle', timeout=30000)
                await asyncio.sleep(3)

                # Extraer contenido completo
                content = await page.evaluate('''() => {
                    return document.body.innerText || '';
                }''')

                print("\n" + "=" * 70)
                print("CONTENIDO DEL DECRETO")
                print("=" * 70)
                print(content[:20000])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
