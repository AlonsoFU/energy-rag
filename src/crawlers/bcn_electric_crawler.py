#!/usr/bin/env python3
"""
BCN Ley Chile - Crawler de Normativa Eléctrica

Busca y extrae normas relacionadas con electricidad/energía
desde la Biblioteca del Congreso Nacional de Chile.

Usa modo headed + stealth para evitar bloqueos.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# Configuración
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"
BASE_URL = "https://www.bcn.cl/leychile"

# Keywords para buscar normativa eléctrica 2025
ELECTRIC_KEYWORDS = [
    "energía 2025",
    "eléctrico 2025",
    "Ministerio Energía 2025",
]

# Filtro de fecha
FECHA_DESDE = "2025-01-01"
YEAR_FILTER = 2025


async def search_bcn(page, keyword: str) -> list:
    """Busca normas en BCN por keyword."""
    print(f"\n  Buscando: '{keyword}'...")

    # URL de búsqueda simple
    search_url = f"{BASE_URL}/Consulta/listaresultadosimple?cadena={quote(keyword)}"

    try:
        await page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)  # Esperar carga JS

        # Verificar si hay resultados
        content = await page.content()

        if "No se encontraron resultados" in content or "0 resultado" in content:
            print(f"    Sin resultados para '{keyword}'")
            return []

        # Extraer normas de la página de resultados
        normas = await page.evaluate('''() => {
            const results = [];

            // Buscar enlaces a normas (tienen idNorma en URL)
            document.querySelectorAll('a[href*="idNorma"]').forEach(a => {
                const href = a.href || '';
                const text = a.textContent.trim();

                // Extraer idNorma de la URL
                const match = href.match(/idNorma=(\d+)/);
                if (match && text.length > 5) {
                    results.push({
                        id_norma: match[1],
                        titulo: text.substring(0, 200),
                        url: href
                    });
                }
            });

            // Buscar fechas asociadas (formato DD-MMM-YYYY o similar)
            const pageText = document.body.innerText;

            return results;
        }''')

        print(f"    Encontradas: {len(normas)} normas")
        return normas

    except Exception as e:
        print(f"    Error buscando '{keyword}': {e}")
        return []


async def get_norm_details(page, id_norma: str) -> dict:
    """Obtiene detalles de una norma específica."""
    url = f"{BASE_URL}/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(2)

        # Extraer metadatos usando JavaScript más simple (sin regex problemáticos)
        details = await page.evaluate('''() => {
            const data = {
                titulo: '',
                tipo_norma: '',
                fecha_publicacion: '',
                fecha_promulgacion: '',
                organismo: '',
                estado: '',
                url_pdf: ''
            };

            // Título - buscar h1 o el título de la norma
            const h1 = document.querySelector('h1');
            if (h1) data.titulo = h1.textContent.trim();

            // Buscar en el texto de la página
            const text = document.body.innerText;
            const lines = text.split('\\n');

            // Buscar líneas con información clave
            for (const line of lines) {
                const trimmed = line.trim();

                // Fecha publicación
                if (trimmed.includes('Fecha Publicación') || trimmed.includes('Fecha de Publicación')) {
                    const parts = trimmed.split(':');
                    if (parts.length > 1) data.fecha_publicacion = parts[1].trim();
                }

                // Fecha promulgación
                if (trimmed.includes('Fecha Promulgación') || trimmed.includes('Promulgación')) {
                    const parts = trimmed.split(':');
                    if (parts.length > 1) data.fecha_promulgacion = parts[1].trim();
                }

                // Organismo
                if (trimmed.includes('Organismo') || trimmed.startsWith('Ministerio')) {
                    if (trimmed.includes(':')) {
                        data.organismo = trimmed.split(':')[1].trim();
                    } else if (trimmed.startsWith('Ministerio')) {
                        data.organismo = trimmed.substring(0, 80);
                    }
                }

                // Tipo de norma
                if (trimmed.includes('Tipo Norma') || trimmed.includes('Tipo de Norma')) {
                    const parts = trimmed.split(':');
                    if (parts.length > 1) data.tipo_norma = parts[1].trim();
                }
            }

            // Estado
            if (text.includes('VIGENTE')) data.estado = 'VIGENTE';
            else if (text.includes('DEROGAD')) data.estado = 'DEROGADA';
            else if (text.includes('Vigente')) data.estado = 'VIGENTE';

            // URL PDF
            const pdfLink = document.querySelector('a[href*=".pdf"]');
            if (pdfLink) data.url_pdf = pdfLink.href;

            // Si no encontró título en h1, buscar en meta o title
            if (!data.titulo) {
                const title = document.querySelector('title');
                if (title) data.titulo = title.textContent.trim();
            }

            return data;
        }''')

        details['id_norma'] = id_norma
        details['url'] = url

        return details

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e)}


def filter_by_year(normas: list, year: int) -> list:
    """Filtra normas por año de publicación o promulgación."""
    filtered = []

    for norma in normas:
        # Verificar fecha_publicacion
        fecha_pub = norma.get('fecha_publicacion', '')
        fecha_prom = norma.get('fecha_promulgacion', '')
        titulo = norma.get('titulo', '') + ' ' + norma.get('keyword_titulo', '')

        # Buscar año en cualquier fecha
        for fecha in [fecha_pub, fecha_prom]:
            if fecha:
                year_match = re.search(r'(\d{4})', fecha)
                if year_match and int(year_match.group(1)) >= year:
                    filtered.append(norma)
                    break
        else:
            # Si no tiene fecha válida, verificar en título
            if str(year) in titulo:
                filtered.append(norma)

    return filtered


async def main():
    print("=" * 60)
    print("BCN Ley Chile - Crawler Normativa Eléctrica")
    print(f"Filtro: Año >= {YEAR_FILTER}")
    print("=" * 60)

    all_normas = {}  # Usar dict para deduplicar por id_norma

    async with async_playwright() as p:
        print("\nLanzando navegador (modo headed)...")

        browser = await p.chromium.launch(
            headless=False,
            args=['--disable-blink-features=AutomationControlled']
        )

        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        # Aplicar stealth
        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        # Fase 1: Buscar por keywords
        print("\n" + "=" * 60)
        print("FASE 1: Búsqueda por keywords")
        print("=" * 60)

        for keyword in ELECTRIC_KEYWORDS:
            normas = await search_bcn(page, keyword)

            for norma in normas:
                id_norma = norma.get('id_norma')
                if id_norma and id_norma not in all_normas:
                    all_normas[id_norma] = norma

            await asyncio.sleep(2)  # Rate limiting

        print(f"\n  Total normas únicas encontradas: {len(all_normas)}")

        # Fase 2: Obtener detalles de cada norma
        print("\n" + "=" * 60)
        print("FASE 2: Extrayendo detalles")
        print("=" * 60)

        detailed_normas = []

        for i, (id_norma, norma) in enumerate(list(all_normas.items())[:50]):  # Limitar a 50 para prueba
            print(f"\n  [{i+1}/{min(50, len(all_normas))}] Procesando norma {id_norma}...")

            details = await get_norm_details(page, id_norma)
            details['keyword_titulo'] = norma.get('titulo', '')
            detailed_normas.append(details)

            await asyncio.sleep(1)  # Rate limiting

        await browser.close()

    # Fase 3: Filtrar por año 2025
    print("\n" + "=" * 60)
    print(f"FASE 3: Filtrando por año >= {YEAR_FILTER}")
    print("=" * 60)

    normas_2025 = filter_by_year(detailed_normas, YEAR_FILTER)

    print(f"\n  Normas {YEAR_FILTER}: {len(normas_2025)}")

    # Guardar resultados
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    # Guardar todas las normas encontradas
    output_all = DATA_RAW / "bcn_normas_electricas_all.json"
    with open(output_all, 'w', encoding='utf-8') as f:
        json.dump(detailed_normas, f, indent=2, ensure_ascii=False)

    # Guardar solo 2025
    output_2025 = DATA_RAW / f"bcn_normas_electricas_{YEAR_FILTER}.json"
    with open(output_2025, 'w', encoding='utf-8') as f:
        json.dump(normas_2025, f, indent=2, ensure_ascii=False)

    # Resumen
    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"\n  Total normas encontradas: {len(all_normas)}")
    print(f"  Normas procesadas: {len(detailed_normas)}")
    print(f"  Normas {YEAR_FILTER}: {len(normas_2025)}")
    print(f"\n  Archivos guardados:")
    print(f"    - {output_all.relative_to(PROJECT_ROOT)}")
    print(f"    - {output_2025.relative_to(PROJECT_ROOT)}")

    # Mostrar normas 2025
    if normas_2025:
        print(f"\n  Normas {YEAR_FILTER} encontradas:")
        for n in normas_2025[:10]:
            titulo = n.get('titulo', n.get('keyword_titulo', 'Sin título'))[:80]
            print(f"    - {titulo}...")

    return {
        'all': detailed_normas,
        f'{YEAR_FILTER}': normas_2025
    }


if __name__ == "__main__":
    asyncio.run(main())
