#!/usr/bin/env python3
"""
BCN - Test simple para verificar acceso y búsqueda.
"""

import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def main():
    print("=" * 60)
    print("BCN - Test de Acceso")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        # Test 1: Acceder a norma conocida de 2025
        print("\n1. Accediendo a norma de 2025...")
        await page.goto(
            "https://www.bcn.cl/leychile/navegar?idNorma=1214493",
            wait_until='networkidle',
            timeout=30000
        )
        await asyncio.sleep(3)

        title = await page.title()
        print(f"   Título página: {title}")

        h1 = await page.query_selector('h1')
        if h1:
            h1_text = await h1.inner_text()
            print(f"   H1: {h1_text[:100]}...")

        # Test 2: Búsqueda simple
        print("\n2. Probando búsqueda 'ley'...")
        await page.goto(
            "https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena=ley",
            wait_until='networkidle',
            timeout=30000
        )
        await asyncio.sleep(3)

        content = await page.content()
        print(f"   Largo contenido: {len(content)} chars")

        # Contar enlaces
        links = await page.query_selector_all('a[href*="idNorma"]')
        print(f"   Enlaces con idNorma: {len(links)}")

        # Test 3: Ver texto de página
        print("\n3. Texto de la página (primeros 500 chars):")
        body_text = await page.inner_text('body')
        print(body_text[:500])

        await browser.close()

    print("\n" + "=" * 60)
    print("Test completado")


if __name__ == "__main__":
    asyncio.run(main())
