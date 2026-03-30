#!/usr/bin/env python3
"""
BCN - Búsqueda completa con paginación.
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def search_and_paginate(page, term: str, max_pages: int = 5):
    """Busca y navega por múltiples páginas de resultados."""

    print(f"\nBuscando: '{term}'")
    print("-" * 40)

    base_url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(term)}"

    all_normas = []

    for page_num in range(1, max_pages + 1):
        # BCN usa offset en la URL para paginar
        offset = (page_num - 1) * 10
        url = f"{base_url}&offset={offset}" if offset > 0 else base_url

        print(f"\n  Página {page_num}...")

        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        # Extraer información de la página
        data = await page.evaluate('''() => {
            const results = [];

            // BCN muestra resultados en una estructura específica
            // Buscar todos los elementos que contienen resultados
            const container = document.body.innerText;

            // Buscar patrones de fecha y norma
            const lines = container.split('\\n');

            let currentNorma = null;

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();

                // Detectar fecha (formato DD-MMM-YYYY)
                const dateMatch = line.match(/^(\\d{2}-[A-Z]{3}-\\d{4})$/i);
                if (dateMatch) {
                    if (currentNorma) {
                        results.push(currentNorma);
                    }
                    currentNorma = {
                        fecha: dateMatch[1],
                        tipo: '',
                        titulo: '',
                        organismo: ''
                    };
                    continue;
                }

                // Si tenemos una norma en proceso, agregar info
                if (currentNorma) {
                    // Detectar tipo de norma
                    if (line.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN|AUTO)/i) && !currentNorma.tipo) {
                        const parts = line.split('\\n');
                        currentNorma.tipo = parts[0];
                        if (parts.length > 1) {
                            currentNorma.titulo = parts.slice(1).join(' ');
                        }
                    }
                    // Detectar organismo (MINISTERIO)
                    else if (line.match(/^MINISTERIO/i) && !currentNorma.organismo) {
                        currentNorma.organismo = line;
                        results.push(currentNorma);
                        currentNorma = null;
                    }
                    // Agregar al título si no tiene
                    else if (!currentNorma.titulo && line.length > 10) {
                        currentNorma.titulo = line.substring(0, 200);
                    }
                }
            }

            if (currentNorma) {
                results.push(currentNorma);
            }

            return results;
        }''')

        # También extraer los enlaces directamente
        links = await page.evaluate('''() => {
            const results = [];
            document.querySelectorAll('a').forEach(a => {
                const href = a.href || '';
                if (href.includes('idNorma=')) {
                    const match = href.match(/idNorma=(\\d+)/);
                    if (match) {
                        results.push({
                            id_norma: match[1],
                            texto: a.textContent.trim().substring(0, 150),
                            url: href
                        });
                    }
                }
            });
            return results;
        }''')

        print(f"    Textos parseados: {len(data)}")
        print(f"    Enlaces encontrados: {len(links)}")

        # Mostrar primeros resultados
        for n in data[:3]:
            print(f"      [{n.get('fecha', '?')}] {n.get('tipo', '?')}: {n.get('titulo', '?')[:40]}...")

        all_normas.extend(data)

        # Si no hay más resultados, parar
        if len(links) == 0:
            print("    (No hay más resultados)")
            break

        await asyncio.sleep(1)

    return all_normas


async def main():
    print("=" * 60)
    print("BCN - Búsqueda con paginación")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        # Buscar Ministerio de Energía (5 páginas = ~50 resultados)
        normas = await search_and_paginate(page, "Ministerio de Energía", max_pages=5)

        await browser.close()

    # Filtrar 2025
    normas_2025 = [n for n in normas if '2025' in n.get('fecha', '')]

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"\nTotal normas encontradas: {len(normas)}")
    print(f"Normas 2025: {len(normas_2025)}")

    if normas_2025:
        print("\nNormas 2025:")
        for n in normas_2025:
            print(f"  [{n['fecha']}] {n.get('tipo', 'N/A')}: {n.get('titulo', 'N/A')[:50]}...")

    # Guardar
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_ministerio_energia.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump({'todas': normas, '2025': normas_2025}, f, indent=2, ensure_ascii=False)

    print(f"\nGuardado: {output}")


if __name__ == "__main__":
    asyncio.run(main())
