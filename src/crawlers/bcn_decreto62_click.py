#!/usr/bin/env python3
"""Acceder al Decreto 62 haciendo click en el resultado."""

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

        # Buscar "APRUEBA REGLAMENTO DE TRANSFERENCIAS DE POTENCIA"
        search = "APRUEBA REGLAMENTO TRANSFERENCIAS POTENCIA EMPRESAS GENERADORAS"
        url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(search)}"

        print(f"Buscando: {search}")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        # Buscar y hacer click en el link que dice "APRUEBA REGLAMENTO"
        clicked = await page.evaluate('''() => {
            const links = document.querySelectorAll('a');
            for (const link of links) {
                const text = link.innerText || '';
                if (text.includes('APRUEBA REGLAMENTO DE TRANSFERENCIAS DE POTENCIA')) {
                    return {
                        found: true,
                        text: text.substring(0, 150),
                        href: link.href
                    };
                }
            }
            // Buscar cualquier link con "62" y "potencia"
            for (const link of links) {
                const text = (link.innerText || '').toLowerCase();
                if (text.includes('62') && text.includes('potencia')) {
                    return {
                        found: true,
                        text: link.innerText.substring(0, 150),
                        href: link.href
                    };
                }
            }
            return {found: false};
        }''')

        if clicked['found']:
            print(f"\nEncontrado: {clicked['text']}")
            print(f"URL: {clicked['href']}")

            # Navegar a ese link
            await page.goto(clicked['href'], wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)

            # Extraer contenido
            content = await page.evaluate('''() => {
                return document.body ? document.body.innerText : '';
            }''')

            print("\n" + "=" * 70)
            print("DECRETO 62 - REGLAMENTO DE TRANSFERENCIAS DE POTENCIA")
            print("=" * 70)
            print(content[:25000])
        else:
            print("No se encontró el decreto")

            # Listar todos los links disponibles
            links = await page.evaluate('''() => {
                const links = document.querySelectorAll('a[href*="navegar"]');
                return Array.from(links).slice(0, 10).map(l => l.innerText.substring(0, 100));
            }''')
            print("\nLinks disponibles:")
            for l in links:
                print(f"  - {l}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
