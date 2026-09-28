#!/usr/bin/env python3
"""
Test para ver cómo BCN estructura las vinculaciones en Decreto 62.
"""

import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def main():
    # Buscar Decreto 62 en normas
    import json
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    # Buscar Decreto 62
    d62 = [n for n in normas.values() if n.get('tipo') == 'DECRETO' and n.get('numero') == '62']

    if d62:
        id_norma = d62[0]['id_norma']
        print(f"Decreto 62 encontrado: ID {id_norma}")
    else:
        # Usar ID conocido
        id_norma = '250604'
        print(f"Usando ID conocido: {id_norma}")

    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        html = await page.content()

        # Guardar HTML para inspección
        with open('data/busquedas/decreto62_html.html', 'w', encoding='utf-8') as f:
            f.write(html)

        # Buscar secciones que mencionen "modific"
        import re
        lineas = html.split('\n')

        print(f"\nLíneas que contienen 'modific' (primeras 20):")
        count = 0
        for i, linea in enumerate(lineas):
            if 'modific' in linea.lower() and count < 20:
                print(f"{i:4}: {linea.strip()[:150]}")
                count += 1

        print(f"\nLíneas que contienen 'vincula' (primeras 20):")
        count = 0
        for i, linea in enumerate(lineas):
            if 'vincula' in linea.lower() and count < 20:
                print(f"{i:4}: {linea.strip()[:150]}")
                count += 1

        await browser.close()

        print(f"\n✅ HTML guardado en: data/busquedas/decreto62_html.html")


if __name__ == "__main__":
    asyncio.run(main())
