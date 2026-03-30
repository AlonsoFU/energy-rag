#!/usr/bin/env python3
"""Extraer contenido del Decreto 62 de Transferencias de Potencia."""

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

        # Decreto 62 - Reglamento de Transferencias de Potencia
        url = "https://www.bcn.cl/leychile/navegar?idNorma=245681"

        print("Cargando Decreto 62...")
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        # Extraer contenido
        content = await page.evaluate('''() => {
            const data = {
                titulo: '',
                fecha: '',
                organismo: '',
                contenido: ''
            };

            // Título
            const titulo = document.querySelector('h1, .titulo-norma, #titulo');
            if (titulo) data.titulo = titulo.innerText.trim();

            // Buscar en el cuerpo
            const body = document.body.innerText || '';
            data.contenido = body;

            return data;
        }''')

        print("\n" + "=" * 70)
        print("DECRETO 62 - TRANSFERENCIAS DE POTENCIA")
        print("=" * 70)
        print(content['contenido'][:15000])

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
