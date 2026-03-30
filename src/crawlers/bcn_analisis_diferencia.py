#!/usr/bin/env python3
"""
BCN - Analizar diferencia entre búsqueda temática vs texto libre.
¿Por qué 113 normas en categoría vs 14,020 en búsqueda?
"""

import asyncio
import json
from pathlib import Path
from collections import Counter
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw"


async def analyze_search_results(page, search_type, url, description):
    """Analiza los resultados de una búsqueda."""
    print(f"\n{'='*60}")
    print(f"{description}")
    print(f"{'='*60}")
    print(f"URL: {url}")

    await page.goto(url, wait_until='networkidle', timeout=30000)
    await asyncio.sleep(3)

    # Extraer información detallada
    analysis = await page.evaluate('''() => {
        const data = {
            total_visible: 0,
            tipos_norma: {},
            organismos: {},
            años: {},
            sample_normas: []
        };

        if (!document.body) return data;
        const text = document.body.innerText || '';
        const lines = text.split('\\n');

        // Buscar total de resultados
        const totalMatch = text.match(/de\\s+([\\d.,]+)\\s*$/m);
        if (totalMatch) {
            data.total_visible = totalMatch[1];
        }

        let currentNorma = null;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i].trim();

            // Fecha (DD-MMM-YYYY)
            const dateMatch = line.match(/^(\\d{2})-([A-Z]{3})-(\\d{4})$/i);
            if (dateMatch) {
                if (currentNorma && currentNorma.tipo) {
                    data.sample_normas.push(currentNorma);

                    // Contar año
                    const year = dateMatch[3];
                    data.años[year] = (data.años[year] || 0) + 1;
                }

                currentNorma = {
                    fecha: line,
                    tipo: '',
                    titulo: '',
                    organismo: ''
                };
                continue;
            }

            if (currentNorma) {
                // Tipo de norma
                if (!currentNorma.tipo) {
                    const tipoMatch = line.match(/^(LEY|DECRETO|DFL|DL|RESOLUCIÓN|AUTO ACORDADO|CIRCULAR)/i);
                    if (tipoMatch) {
                        const tipo = tipoMatch[1].toUpperCase();
                        data.tipos_norma[tipo] = (data.tipos_norma[tipo] || 0) + 1;
                        currentNorma.tipo = line.substring(0, 100);
                        continue;
                    }
                }

                // Organismo (MINISTERIO)
                if (line.match(/^MINISTERIO|^SUBSECRETARIA|^SUPERINTENDENCIA|^COMISIÓN/i)) {
                    const org = line.substring(0, 60);
                    data.organismos[org] = (data.organismos[org] || 0) + 1;
                    currentNorma.organismo = org;
                }

                // Título
                if (currentNorma.tipo && !currentNorma.titulo && line.length > 20) {
                    currentNorma.titulo = line.substring(0, 150);
                }
            }
        }

        if (currentNorma && currentNorma.tipo) {
            data.sample_normas.push(currentNorma);
        }

        return data;
    }''')

    print(f"\nTotal indicado: {analysis['total_visible']}")
    print(f"Normas en página: {len(analysis['sample_normas'])}")

    print("\n  TIPOS DE NORMA:")
    for tipo, count in sorted(analysis['tipos_norma'].items(), key=lambda x: -x[1]):
        print(f"    {tipo}: {count}")

    print("\n  ORGANISMOS:")
    for org, count in sorted(analysis['organismos'].items(), key=lambda x: -x[1])[:10]:
        print(f"    {org}: {count}")

    print("\n  AÑOS:")
    for year, count in sorted(analysis['años'].items(), key=lambda x: -int(x[0]))[:10]:
        print(f"    {year}: {count}")

    print("\n  MUESTRA DE NORMAS:")
    for n in analysis['sample_normas'][:5]:
        print(f"    [{n['fecha']}] {n['tipo'][:40]}")
        if n['titulo']:
            print(f"      → {n['titulo'][:60]}...")

    return analysis


async def main():
    print("=" * 60)
    print("ANÁLISIS: ¿Por qué 113 vs 14,020?")
    print("=" * 60)

    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # 1. Categoría temática "ENERGÍA"
        results['tematica'] = await analyze_search_results(
            page,
            "tematica",
            "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=2&sub=1137",
            "1. CATEGORÍA TEMÁTICA: ENERGÍA (113 normas curadas)"
        )

        # 2. Búsqueda texto libre "energía"
        results['texto_libre'] = await analyze_search_results(
            page,
            "texto",
            "https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena=energ%C3%ADa",
            "2. BÚSQUEDA TEXTO LIBRE: 'energía' (14,020 resultados)"
        )

        # 3. Búsqueda más específica "servicios eléctricos"
        results['electricos'] = await analyze_search_results(
            page,
            "texto",
            "https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena=servicios%20el%C3%A9ctricos",
            "3. BÚSQUEDA: 'servicios eléctricos'"
        )

        # 4. Búsqueda por organismo "Ministerio de Energía"
        results['ministerio'] = await analyze_search_results(
            page,
            "texto",
            "https://www.bcn.cl/leychile/Consulta/listaresultadosimple?cadena=Ministerio%20de%20Energ%C3%ADa",
            "4. BÚSQUEDA: 'Ministerio de Energía'"
        )

        await browser.close()

    # Guardar
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    output = DATA_RAW / "bcn_analisis_diferencia.json"
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Conclusiones
    print("\n" + "=" * 60)
    print("CONCLUSIONES")
    print("=" * 60)

    print("""
    La diferencia entre 113 y 14,020 se debe a:

    1. CATEGORÍA TEMÁTICA (113):
       - Selección CURADA de leyes principales sobre energía
       - Solo leyes fundamentales del sector
       - Mantenida manualmente por BCN

    2. BÚSQUEDA TEXTO LIBRE (14,020):
       - CUALQUIER norma que mencione "energía" en su texto
       - Incluye resoluciones menores, decretos administrativos
       - Incluye normas donde energía es secundaria
       - Ej: "...ahorro de energía en edificios..."

    RECOMENDACIÓN:
    - Para normas CLAVE del sector: usar categorías temáticas
    - Para búsqueda EXHAUSTIVA: usar texto libre + filtros
    """)


if __name__ == "__main__":
    asyncio.run(main())
