#!/usr/bin/env python3
"""
Buscar IDs de normas usando búsqueda web, luego ir directo a BCN.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# Términos de búsqueda con contexto
BUSQUEDAS = [
    # Distribución
    "bcn.cl decreto tarifas distribucion electrica",
    "bcn.cl decreto valor agregado distribucion VAD",
    "bcn.cl ley distribucion electrica",

    # Peajes transmisión
    "bcn.cl decreto peajes transmision electrica",
    "bcn.cl decreto remuneracion transmision",

    # Servicios complementarios
    "bcn.cl decreto servicios complementarios electricos",
    "bcn.cl decreto reserva control frecuencia",

    # Medición
    "bcn.cl decreto medidores electricos inteligentes",
    "bcn.cl resolucion medicion electrica",

    # Transferencias energía
    "bcn.cl decreto transferencias energia electrica costo marginal",
]


async def buscar_ids_en_web(query: str, page) -> list:
    """Buscar en DuckDuckGo y extraer IDs de BCN."""
    ids = []

    try:
        url = f"https://duckduckgo.com/html/?q={query.replace(' ', '+')}"
        await page.goto(url, wait_until='networkidle', timeout=20000)
        await asyncio.sleep(1)

        html = await page.content()

        # Extraer idNorma de los resultados
        matches = re.findall(r'bcn\.cl[^"]*idNorma[=:](\d+)', html)
        ids = list(set(matches))[:5]  # Máximo 5 por búsqueda

    except Exception as e:
        print(f"      Error: {e}")

    return ids


async def obtener_norma_bcn(id_norma: str, page) -> dict:
    """Obtener detalles de una norma de BCN."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=25000)
        await asyncio.sleep(1)

        html = await page.content()

        # Título
        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1) if title_match else ""

        # Tipo y número
        norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.I)
        tipo = norm_match.group(1).upper() if norm_match else "?"
        numero = norm_match.group(2) if norm_match else "?"
        if tipo == 'DTO': tipo = 'DECRETO'

        # Temas
        texto = html.lower()
        temas = []
        if 'distribuci' in texto: temas.append('DISTRIBUCION')
        if 'transmisi' in texto: temas.append('TRANSMISION')
        if 'peaje' in texto: temas.append('PEAJES')
        if 'complementari' in texto: temas.append('SSCC')
        if 'medid' in texto: temas.append('MEDICION')
        if 'potencia' in texto: temas.append('POTENCIA')
        if 'tarifa' in texto: temas.append('TARIFAS')
        if 'energ' in texto: temas.append('ENERGIA')

        return {
            'id_norma': id_norma,
            'tipo': tipo,
            'numero': numero,
            'titulo': titulo[:150],
            'temas': temas
        }

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e)}


async def main():
    print("=" * 70)
    print("BÚSQUEDA DE NORMAS VÍA WEB")
    print("=" * 70)

    todos_ids = set()
    normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Buscar IDs
        for i, query in enumerate(BUSQUEDAS, 1):
            tema = query.split("bcn.cl ")[1][:30] if "bcn.cl " in query else query[:30]
            print(f"\n[{i}/{len(BUSQUEDAS)}] {tema}...")

            ids = await buscar_ids_en_web(query, page)
            print(f"    IDs encontrados: {ids}")

            todos_ids.update(ids)
            await asyncio.sleep(1)

        print(f"\n{'=' * 70}")
        print(f"Total IDs únicos: {len(todos_ids)}")
        print(f"{'=' * 70}")

        # Obtener detalles de cada ID
        for i, id_norma in enumerate(list(todos_ids)[:30], 1):
            print(f"\n[{i}] Obteniendo {id_norma}...")

            info = await obtener_norma_bcn(id_norma, page)

            if 'error' not in info:
                normas[id_norma] = info
                print(f"    ✓ {info['tipo']} {info['numero']}: {info['temas']}")
            else:
                print(f"    ✗ Error")

            await asyncio.sleep(0.5)

        await browser.close()

    # Guardar
    output = {
        'fecha': datetime.now().isoformat(),
        'total': len(normas),
        'normas': list(normas.values())
    }

    output_path = Path("data/busquedas/normas_temas_electricos.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Resumen por tema
    print(f"\n{'=' * 70}")
    print("RESUMEN POR TEMA")
    print(f"{'=' * 70}")

    from collections import defaultdict
    por_tema = defaultdict(list)

    for n in normas.values():
        for t in n.get('temas', []):
            por_tema[t].append(f"{n['tipo']} {n['numero']}")

    for tema, lista in sorted(por_tema.items(), key=lambda x: -len(x[1])):
        print(f"\n{tema} ({len(lista)}):")
        for n in lista[:5]:
            print(f"  - {n}")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
