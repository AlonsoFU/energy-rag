#!/usr/bin/env python3
"""
BCN Ley Chile - Scraper de Normativa Energética 2025

Busca y extrae normas del sector energético/eléctrico publicadas en 2025.
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

# Términos de búsqueda específicos para energía
SEARCH_TERMS = [
    "Ministerio de Energía",
    "energía eléctrica",
    "servicios eléctricos",
    "transmisión eléctrica",
    "Coordinador Eléctrico Nacional",
    "CNE",
]

YEAR_FILTER = 2025


async def search_and_extract(page, term: str) -> list:
    """Busca normas y extrae las que contienen 2025."""
    print(f"\n  Buscando: '{term}'...")

    search_url = f"{BASE_URL}/Consulta/listaresultadosimple?cadena={quote(term)}"

    try:
        await page.goto(search_url, wait_until='networkidle', timeout=45000)
        await asyncio.sleep(3)

        # Extraer normas de la página
        normas = await page.evaluate('''(year) => {
            const results = [];
            const yearStr = year.toString();

            // Buscar todos los enlaces a normas
            document.querySelectorAll('a[href*="idNorma"]').forEach(a => {
                const href = a.href || '';
                const text = a.textContent.trim();

                // Obtener contexto (fecha, organismo, etc.)
                const parent = a.closest('tr') || a.closest('li') || a.closest('div');
                const context = parent ? parent.innerText : '';

                // Solo incluir si menciona el año
                if (context.includes(yearStr) || text.includes(yearStr)) {
                    const match = href.match(/idNorma=(\\d+)/);
                    if (match && text.length > 3) {
                        // Extraer fecha si está visible
                        const dateMatch = context.match(/(\\d{2}-[A-Z]{3}-\\d{4})/i);

                        results.push({
                            id_norma: match[1],
                            titulo: text.substring(0, 250),
                            fecha_visible: dateMatch ? dateMatch[1] : '',
                            contexto: context.substring(0, 300),
                            url: href
                        });
                    }
                }
            });

            return results;
        }''', YEAR_FILTER)

        print(f"    Encontradas con {YEAR_FILTER}: {len(normas)}")
        return normas

    except Exception as e:
        print(f"    Error: {e}")
        return []


async def get_norm_details(page, id_norma: str) -> dict:
    """Extrae metadatos completos de una norma."""
    url = f"{BASE_URL}/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        # Extraer metadatos
        details = await page.evaluate('''() => {
            const data = {
                titulo_completo: '',
                tipo_norma: '',
                fecha_publicacion: '',
                fecha_promulgacion: '',
                organismo: '',
                estado: '',
                materias: ''
            };

            // Título desde h1
            const h1 = document.querySelector('h1');
            if (h1) data.titulo_completo = h1.innerText.trim();

            // Buscar tabla de datos o texto estructurado
            const bodyText = document.body.innerText;

            // Parsear por patrones comunes de BCN
            const patterns = {
                'Tipo Norma': 'tipo_norma',
                'Fecha Publicación': 'fecha_publicacion',
                'Fecha Promulgación': 'fecha_promulgacion',
                'Organismo': 'organismo',
                'Materias': 'materias'
            };

            for (const [pattern, field] of Object.entries(patterns)) {
                const regex = new RegExp(pattern + '[:\\s]+([^\\n]+)', 'i');
                const match = bodyText.match(regex);
                if (match) {
                    data[field] = match[1].trim().substring(0, 200);
                }
            }

            // Estado
            if (bodyText.includes('Vigente') || bodyText.includes('VIGENTE')) {
                data.estado = 'VIGENTE';
            } else if (bodyText.includes('DEROGAD')) {
                data.estado = 'DEROGADA';
            }

            return data;
        }''')

        details['id_norma'] = id_norma
        details['url'] = url

        return details

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e), 'url': url}


def is_energy_related(norma: dict) -> bool:
    """Verifica si la norma está relacionada con energía/electricidad."""
    keywords = [
        'energía', 'eléctric', 'electricidad', 'transmisión',
        'generación', 'CNE', 'SEC', 'Coordinador', 'tarifa',
        'suministro', 'potencia', 'voltaje', 'kilowatt'
    ]

    text = ' '.join([
        norma.get('titulo_completo', ''),
        norma.get('materias', ''),
        norma.get('organismo', ''),
        norma.get('contexto', '')
    ]).lower()

    return any(kw.lower() in text for kw in keywords)


async def main():
    print("=" * 60)
    print(f"BCN Ley Chile - Normativa Energética {YEAR_FILTER}")
    print("=" * 60)

    all_normas = {}

    async with async_playwright() as p:
        print("\nLanzando navegador...")

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

        # Fase 1: Buscar por términos
        print("\n" + "-" * 40)
        print("FASE 1: Búsqueda por términos")
        print("-" * 40)

        for term in SEARCH_TERMS:
            normas = await search_and_extract(page, term)

            for n in normas:
                id_norma = n.get('id_norma')
                if id_norma and id_norma not in all_normas:
                    all_normas[id_norma] = n

            await asyncio.sleep(2)

        print(f"\n  Total normas únicas {YEAR_FILTER}: {len(all_normas)}")

        # Fase 2: Obtener detalles
        if all_normas:
            print("\n" + "-" * 40)
            print("FASE 2: Extrayendo detalles")
            print("-" * 40)

            detailed = []
            for i, (id_norma, n) in enumerate(all_normas.items()):
                print(f"  [{i+1}/{len(all_normas)}] Norma {id_norma}...")

                details = await get_norm_details(page, id_norma)
                details['fecha_busqueda'] = n.get('fecha_visible', '')
                details['contexto_busqueda'] = n.get('contexto', '')
                detailed.append(details)

                await asyncio.sleep(1)

            # Filtrar solo relacionadas con energía
            energy_normas = [n for n in detailed if is_energy_related(n)]
            print(f"\n  Normas relacionadas con energía: {len(energy_normas)}")

        else:
            detailed = []
            energy_normas = []

        await browser.close()

    # Guardar resultados
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    # Guardar todas las de 2025
    output_all = DATA_RAW / f"bcn_todas_{YEAR_FILTER}.json"
    with open(output_all, 'w', encoding='utf-8') as f:
        json.dump(detailed, f, indent=2, ensure_ascii=False)

    # Guardar solo energía
    output_energy = DATA_RAW / f"bcn_energia_{YEAR_FILTER}.json"
    with open(output_energy, 'w', encoding='utf-8') as f:
        json.dump(energy_normas, f, indent=2, ensure_ascii=False)

    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"\n  Normas {YEAR_FILTER} totales: {len(detailed)}")
    print(f"  Normas energía: {len(energy_normas)}")
    print(f"\n  Archivos:")
    print(f"    - {output_all.name}")
    print(f"    - {output_energy.name}")

    if energy_normas:
        print(f"\n  Normas energía {YEAR_FILTER}:")
        for n in energy_normas[:10]:
            titulo = n.get('titulo_completo', '')[:60]
            tipo = n.get('tipo_norma', 'N/A')
            fecha = n.get('fecha_publicacion', n.get('fecha_promulgacion', ''))
            print(f"    [{fecha}] {tipo}: {titulo}...")

    return {'all': detailed, 'energy': energy_normas}


if __name__ == "__main__":
    asyncio.run(main())
