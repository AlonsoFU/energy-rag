#!/usr/bin/env python3
"""Extraer Decreto 62 desde URL conocida."""

import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # URL correcta del Decreto 62
        url = "https://www.bcn.cl/leychile/navegar?idNorma=250604"

        print(f"Accediendo a: {url}")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(4)

        # Extraer contenido
        content = await page.evaluate('''() => {
            return document.body ? document.body.innerText : '';
        }''')

        print("\n" + "=" * 70)
        print("DECRETO 62 - REGLAMENTO DE TRANSFERENCIAS DE POTENCIA")
        print("=" * 70)
        print(content)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
