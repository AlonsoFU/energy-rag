#!/usr/bin/env python3
"""
Extraer la sección "Vinculaciones" estructurada de BCN.
Esta sección contiene:
- Modifica a
- Modificada por
- Deroga a
- Derogada por
- Reglamenta
"""

import asyncio
import json
import re
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def extraer_vinculaciones_estructuradas(id_norma: str, page) -> dict:
    """
    Extrae vinculaciones estructuradas de la página de BCN.
    """
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1)
        html = await page.content()

        vinculaciones = {
            'modifica_a': [],
            'modificada_por': [],
            'deroga_a': [],
            'derogada_por': [],
            'reglamenta': [],
            'reglamentada_por': []
        }

        # Extraer texto limpio
        # Remover tags HTML
        texto = re.sub(r'<[^>]+>', '\n', html)

        # Buscar patrones de vinculación
        lineas = texto.split('\n')

        for i, linea in enumerate(lineas):
            linea_lower = linea.lower().strip()

            # Modificaciones
            if 'modifica' in linea_lower and 'por' not in linea_lower:
                # Buscar IDs en líneas siguientes
                for j in range(i, min(i+5, len(lineas))):
                    ids = re.findall(r'idNorma=(\d+)', lineas[j])
                    if ids:
                        vinculaciones['modifica_a'].extend(ids)

            if 'modificad' in linea_lower and 'por' in linea_lower:
                for j in range(i, min(i+5, len(lineas))):
                    ids = re.findall(r'idNorma=(\d+)', lineas[j])
                    if ids:
                        vinculaciones['modificada_por'].extend(ids)

            # Derogaciones
            if 'deroga' in linea_lower and 'por' not in linea_lower:
                for j in range(i, min(i+5, len(lineas))):
                    ids = re.findall(r'idNorma=(\d+)', lineas[j])
                    if ids:
                        vinculaciones['deroga_a'].extend(ids)

            if 'derogad' in linea_lower and 'por' in linea_lower:
                for j in range(i, min(i+5, len(lineas))):
                    ids = re.findall(r'idNorma=(\d+)', lineas[j])
                    if ids:
                        vinculaciones['derogada_por'].extend(ids)

            # Reglamentaciones
            if 'reglamenta' in linea_lower and 'por' not in linea_lower:
                for j in range(i, min(i+5, len(lineas))):
                    ids = re.findall(r'idNorma=(\d+)', lineas[j])
                    if ids:
                        vinculaciones['reglamenta'].extend(ids)

            if 'reglamentad' in linea_lower and 'por' in linea_lower:
                for j in range(i, min(i+5, len(lineas))):
                    ids = re.findall(r'idNorma=(\d+)', lineas[j])
                    if ids:
                        vinculaciones['reglamentada_por'].extend(ids)

        # Limpiar duplicados
        for key in vinculaciones:
            vinculaciones[key] = list(set(vinculaciones[key]))

        return {
            'id_norma': id_norma,
            'vinculaciones_estructuradas': vinculaciones,
            'url': url
        }

    except Exception as e:
        return {
            'id_norma': id_norma,
            'error': str(e)[:100],
            'url': url
        }


async def main():
    # Cargar normas
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    # Seleccionar normas clave del sector eléctrico para probar
    # Priorizar las más importantes
    normas_electricas = [
        n for n in normas.values()
        if n.get('temas_detectados') and len(n.get('vinculaciones_ids', [])) > 0
    ]

    # Ordenar por número de vinculaciones (las más conectadas primero)
    normas_electricas.sort(key=lambda x: -len(x.get('vinculaciones_ids', [])))

    # Tomar las primeras 50 para empezar
    muestra = normas_electricas[:50]

    print(f"Extrayendo vinculaciones estructuradas de {len(muestra)} normas clave...\n")

    resultados = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, norma in enumerate(muestra, 1):
            id_norma = norma['id_norma']
            print(f"[{i}/{len(muestra)}] {norma['tipo']} {norma['numero']}...", end=" ")

            vinc = await extraer_vinculaciones_estructuradas(id_norma, page)

            if 'error' not in vinc:
                v = vinc['vinculaciones_estructuradas']
                total = sum(len(v[k]) for k in v)
                print(f"✓ {total} vinculaciones estructuradas")

                if total > 0:
                    print(f"    Modifica: {len(v['modifica_a'])}, Modificada por: {len(v['modificada_por'])}")
                    print(f"    Deroga: {len(v['deroga_a'])}, Derogada por: {len(v['derogada_por'])}")
                    print(f"    Reglamenta: {len(v['reglamenta'])}, Reglamentada por: {len(v['reglamentada_por'])}")

                resultados[id_norma] = vinc
            else:
                print(f"ERROR: {vinc['error'][:40]}")

            await asyncio.sleep(1)

        await browser.close()

    # Guardar resultados
    with open('data/busquedas/vinculaciones_estructuradas.json', 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print(f"✅ Vinculaciones estructuradas guardadas")
    print(f"   Total normas procesadas: {len(resultados)}")
    print(f"   Archivo: data/busquedas/vinculaciones_estructuradas.json")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
