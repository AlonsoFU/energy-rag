#!/usr/bin/env python3
"""
BCN - Buscar normas relacionadas a transferencias de potencia y LGSE.
Últimos 5 años (2020-2025).
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"

# Términos relacionados al Decreto 62
SEARCH_TERMS = [
    "transferencias de potencia",
    "empresas generadoras",
    "Ley General de Servicios Eléctricos",
    "potencia eléctrica",
    "generación eléctrica",
    "sistema eléctrico nacional",
    "Coordinador Eléctrico",
    "suministro eléctrico",
    "tarifas eléctricas",
    "transmisión eléctrica",
]

# Años a considerar
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]


async def search_and_extract(page, term: str) -> list:
    """Busca y extrae normas de los últimos 5 años."""
    print(f"\n  Buscando: '{term}'...")

    url = f"https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena={quote(term)}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        # Extraer normas
        normas = await page.evaluate('''(years) => {
            const results = [];
            if (!document.body) return results;

            const text = document.body.innerText || '';
            const lines = text.split('\\n');

            let current = null;

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();

                // Fecha
                const dateMatch = line.match(/^(\\d{2})-([A-Z]{3})-(\\d{4})$/i);
                if (dateMatch) {
                    if (current && current.tipo) {
                        results.push(current);
                    }

                    const year = parseInt(dateMatch[3]);
                    current = {
                        fecha: line,
                        año: year,
                        tipo: '',
                        titulo: '',
                        organismo: ''
                    };
                    continue;
                }

                if (current) {
                    // Tipo de norma
                    if (!current.tipo) {
                        const tipoMatch = line.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN)/i);
                        if (tipoMatch) {
                            current.tipo = line.substring(0, 150);
                            continue;
                        }
                    }

                    // Título
                    if (current.tipo && !current.titulo && line.length > 20 &&
                        !line.match(/^MINISTERIO|^Alertas|^Vinculaciones/)) {
                        current.titulo = line.substring(0, 250);
                    }

                    // Organismo
                    if (line.match(/^MINISTERIO/i)) {
                        current.organismo = line.substring(0, 100);
                    }
                }
            }

            if (current && current.tipo) {
                results.push(current);
            }

            // Filtrar por años
            return results.filter(n => years.includes(n.año));
        }''', YEARS)

        print(f"    Encontradas (2020-2025): {len(normas)}")
        return normas

    except Exception as e:
        print(f"    Error: {e}")
        return []


async def main():
    print("=" * 60)
    print("BCN - Normas relacionadas a LGSE y Potencia (2020-2025)")
    print("=" * 60)
    print(f"\nReferencia: Decreto 62 - Transferencias de Potencia")
    print(f"Años: {YEARS}")

    all_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for term in SEARCH_TERMS:
            normas = await search_and_extract(page, term)

            for n in normas:
                # Crear key única
                key = f"{n['fecha']}_{n['tipo'][:30]}"
                if key not in all_normas:
                    n['busqueda'] = term
                    all_normas[key] = n

            await asyncio.sleep(2)

        await browser.close()

    # Convertir a lista y ordenar por fecha
    normas_list = list(all_normas.values())
    normas_list.sort(key=lambda x: (x['año'], x['fecha']), reverse=True)

    # Guardar
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_lgse_potencia_2020_2025.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(normas_list, f, indent=2, ensure_ascii=False)

    # Resumen
    print("\n" + "=" * 60)
    print("RESULTADOS")
    print("=" * 60)

    # Por año
    by_year = {}
    for n in normas_list:
        year = n['año']
        by_year[year] = by_year.get(year, 0) + 1

    print(f"\nTotal normas únicas: {len(normas_list)}")
    print("\nPor año:")
    for year in sorted(by_year.keys(), reverse=True):
        print(f"  {year}: {by_year[year]} normas")

    # Por tipo
    by_type = {}
    for n in normas_list:
        tipo = n['tipo'].split()[0] if n['tipo'] else 'OTRO'
        by_type[tipo] = by_type.get(tipo, 0) + 1

    print("\nPor tipo:")
    for tipo, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {tipo}: {count}")

    # Mostrar todas
    print("\n" + "=" * 60)
    print("LISTADO COMPLETO")
    print("=" * 60)

    for n in normas_list:
        print(f"\n[{n['fecha']}] {n['tipo']}")
        if n['titulo']:
            print(f"  {n['titulo'][:80]}...")
        if n['organismo']:
            print(f"  → {n['organismo'][:60]}")

    print(f"\n\nGuardado: {output}")

    return normas_list


if __name__ == "__main__":
    asyncio.run(main())
