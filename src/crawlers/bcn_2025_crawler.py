#!/usr/bin/env python3
"""
BCN Ley Chile - Crawler de Normas 2025 (Energía/Electricidad)

Busca normas del sector eléctrico publicadas en 2025.
Usa búsqueda avanzada de BCN con filtros de fecha.
"""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configuración
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
BASE_URL = "https://www.bcn.cl/leychile"

# Términos de búsqueda para sector eléctrico
SEARCH_TERMS = [
    "energía",
    "eléctrico",
    "electricidad",
    "transmisión",
    "generación",
    "distribución eléctrica",
]

YEAR = 2025


async def search_with_advanced_filters(page, term: str) -> list:
    """
    Busca en BCN usando el buscador y filtra por año.
    """
    print(f"\n  Buscando: '{term}'...")

    search_url = f"{BASE_URL}/Consulta/listaresultadosimple?cadena={quote(term)}"

    try:
        await page.goto(search_url, wait_until='networkidle', timeout=45000)
        await asyncio.sleep(4)

        # Verificar contenido
        content = await page.content()

        if "No se encontraron" in content or "0 resultado" in content:
            print(f"    Sin resultados")
            return []

        # Extraer todas las normas de la página
        normas = await page.evaluate('''() => {
            const results = [];

            // Buscar todos los enlaces con idNorma
            document.querySelectorAll('a[href*="idNorma"]').forEach(a => {
                const href = a.href || '';
                const text = a.textContent.trim();
                const parent = a.closest('tr') || a.closest('div') || a.parentElement;
                const parentText = parent ? parent.innerText : '';

                // Extraer idNorma
                const match = href.match(/idNorma=(\\d+)/);
                if (match && text.length > 3) {
                    results.push({
                        id_norma: match[1],
                        titulo: text.substring(0, 300),
                        contexto: parentText.substring(0, 500),
                        url: href
                    });
                }
            });

            return results;
        }''')

        # Filtrar por 2025 en el contexto o título
        normas_2025 = []
        for n in normas:
            texto = n.get('titulo', '') + ' ' + n.get('contexto', '')
            if '2025' in texto or '-2025' in texto:
                normas_2025.append(n)

        print(f"    Total: {len(normas)}, 2025: {len(normas_2025)}")
        return normas_2025

    except Exception as e:
        print(f"    Error: {e}")
        return []


async def get_norm_details(page, id_norma: str) -> dict:
    """Obtiene detalles completos de una norma."""
    url = f"{BASE_URL}/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        details = await page.evaluate('''() => {
            const data = {
                titulo: '',
                tipo_norma: '',
                numero: '',
                fecha_publicacion: '',
                fecha_promulgacion: '',
                organismo: '',
                estado: '',
                materias: '',
                resumen: ''
            };

            // Título
            const h1 = document.querySelector('h1');
            if (h1) data.titulo = h1.textContent.trim();

            // Buscar en el texto completo
            const text = document.body.innerText;

            // Parsear información por líneas
            const lines = text.split('\\n');
            for (const line of lines) {
                const t = line.trim();

                if (t.startsWith('Tipo Norma')) {
                    data.tipo_norma = t.replace('Tipo Norma', '').replace(':', '').trim();
                }
                if (t.startsWith('Fecha Publicación')) {
                    data.fecha_publicacion = t.replace('Fecha Publicación', '').replace(':', '').trim();
                }
                if (t.startsWith('Fecha Promulgación')) {
                    data.fecha_promulgacion = t.replace('Fecha Promulgación', '').replace(':', '').trim();
                }
                if (t.startsWith('Organismo')) {
                    data.organismo = t.replace('Organismo', '').replace(':', '').trim();
                }
                if (t.startsWith('Materias')) {
                    data.materias = t.replace('Materias', '').replace(':', '').trim();
                }
            }

            // Estado
            if (text.includes('VIGENTE')) data.estado = 'VIGENTE';
            else if (text.includes('DEROGAD')) data.estado = 'DEROGADA';

            return data;
        }''')

        details['id_norma'] = id_norma
        details['url'] = url

        return details

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e), 'url': url}


async def main():
    print("=" * 60)
    print(f"BCN Ley Chile - Normas Sector Eléctrico {YEAR}")
    print("=" * 60)

    all_normas = {}

    async with async_playwright() as p:
        print("\nLanzando navegador (modo headed)...")

        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        )

        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        # Buscar por cada término
        print("\n" + "=" * 60)
        print("BÚSQUEDA POR TÉRMINOS")
        print("=" * 60)

        for term in SEARCH_TERMS:
            normas = await search_with_advanced_filters(page, term)

            for n in normas:
                id_norma = n.get('id_norma')
                if id_norma and id_norma not in all_normas:
                    all_normas[id_norma] = n

            await asyncio.sleep(2)

        print(f"\n  Normas únicas {YEAR}: {len(all_normas)}")

        # Obtener detalles
        if all_normas:
            print("\n" + "=" * 60)
            print("EXTRAYENDO DETALLES")
            print("=" * 60)

            detailed = []
            for i, (id_norma, n) in enumerate(all_normas.items()):
                print(f"\n  [{i+1}/{len(all_normas)}] {id_norma}...")
                details = await get_norm_details(page, id_norma)
                details['busqueda_titulo'] = n.get('titulo', '')
                detailed.append(details)
                await asyncio.sleep(1)
        else:
            detailed = []

        await browser.close()

    # Guardar resultados
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    output_file = DATA_RAW / f"bcn_energia_{YEAR}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(detailed, f, indent=2, ensure_ascii=False)

    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"\n  Normas {YEAR} encontradas: {len(detailed)}")
    print(f"  Archivo: {output_file.relative_to(PROJECT_ROOT)}")

    if detailed:
        print(f"\n  Normas encontradas:")
        for n in detailed[:15]:
            titulo = n.get('titulo', n.get('busqueda_titulo', ''))[:70]
            fecha = n.get('fecha_publicacion', n.get('fecha_promulgacion', ''))
            print(f"    [{fecha}] {titulo}...")

    return detailed


if __name__ == "__main__":
    asyncio.run(main())
