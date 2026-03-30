#!/usr/bin/env python3
"""
Buscar normas para TODOS los temas de transacciones económicas.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# Temas a buscar con términos específicos
TEMAS = {
    "TRANSFERENCIAS_ENERGIA": [
        "transferencias energia electrica",
        "balance energia",
        "costo marginal energia",
    ],
    "PEAJES_TRANSMISION": [
        "peaje transmision",
        "pago transmision electrica",
        "remuneracion transmision",
        "sistema transmision nacional",
    ],
    "SERVICIOS_COMPLEMENTARIOS": [
        "servicios complementarios electricos",
        "reserva frecuencia",
        "control frecuencia",
        "servicios auxiliares electricos",
    ],
    "DISTRIBUCION": [
        "distribucion electrica",
        "tarifas distribucion",
        "empresa distribuidora electrica",
        "concesion distribucion",
        "valor agregado distribucion",
    ],
    "MEDIDAS_MEDICION": [
        "medidores electricos",
        "medicion electrica",
        "sistema medicion",
        "lectura medidores",
        "metering electrico",
    ],
}


async def buscar_en_google_bcn(termino: str, page) -> list:
    """Buscar en Google restringido a BCN."""
    results = []

    # Usar Google con site:bcn.cl
    query = f"site:bcn.cl/leychile {termino}"
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        html = await page.content()

        # Buscar links a BCN con idNorma
        pattern = r'bcn\.cl/leychile[^"]*idNorma=(\d+)'
        ids = set(re.findall(pattern, html))

        for id_norma in ids:
            results.append({'id_norma': id_norma, 'fuente': 'google'})

    except Exception as e:
        print(f"      Error Google: {e}")

    return results


async def buscar_directo_bcn(termino: str, page) -> list:
    """Buscar directamente en BCN con el formulario."""
    results = []

    try:
        # Ir a BCN
        await page.goto("https://www.bcn.cl/leychile", wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1)

        # Buscar input de búsqueda
        search_selectors = [
            'input[type="text"]',
            'input[type="search"]',
            'input[placeholder*="uscar"]',
            '#txtBuscador',
            'input[name="txtBuscador"]',
        ]

        for selector in search_selectors:
            try:
                input_elem = await page.query_selector(selector)
                if input_elem:
                    await input_elem.fill(termino)
                    await input_elem.press('Enter')
                    await asyncio.sleep(3)
                    break
            except:
                continue

        html = await page.content()

        # Extraer idNorma de los resultados
        pattern = r'idNorma=(\d+)'
        ids = set(re.findall(pattern, html))

        # Para cada ID, intentar obtener tipo y número
        for id_norma in list(ids)[:20]:
            context = re.search(rf'idNorma={id_norma}[^"]*"[^>]*>([^<]+)', html)
            if context:
                texto = context.group(1)
                norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RES)\s*N?[°º]?\s*(\d+)', texto, re.I)
                if norm_match:
                    tipo = norm_match.group(1).upper()
                    if tipo == 'DTO': tipo = 'DECRETO'
                    if tipo == 'RES': tipo = 'RESOLUCION'
                    results.append({
                        'id_norma': id_norma,
                        'tipo': tipo,
                        'numero': norm_match.group(2),
                        'texto': texto[:100]
                    })

    except Exception as e:
        print(f"      Error BCN: {e}")

    return results


async def explorar_norma_detalle(id_norma: str, page) -> dict:
    """Obtener detalles de una norma específica."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1.5)

        html = await page.content()

        # Extraer título
        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1) if title_match else ""

        # Extraer tipo y número del título o contenido
        norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.I)

        if norm_match:
            tipo = norm_match.group(1).upper()
            if tipo == 'DTO': tipo = 'DECRETO'
            numero = norm_match.group(2)
        else:
            tipo = "DESCONOCIDO"
            numero = ""

        # Detectar temas en el contenido
        texto_lower = html.lower()
        temas = []

        if 'distribuci' in texto_lower: temas.append('DISTRIBUCION')
        if 'transmisi' in texto_lower: temas.append('TRANSMISION')
        if 'generaci' in texto_lower: temas.append('GENERACION')
        if 'medid' in texto_lower or 'medici' in texto_lower: temas.append('MEDICION')
        if 'peaje' in texto_lower: temas.append('PEAJES')
        if 'complementari' in texto_lower: temas.append('SSCC')
        if 'tarifa' in texto_lower: temas.append('TARIFAS')
        if 'potencia' in texto_lower: temas.append('POTENCIA')
        if 'energia' in texto_lower or 'energía' in texto_lower: temas.append('ENERGIA')

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
    print("BÚSQUEDA COMPLETA: TODOS LOS TEMAS DE TRANSACCIONES")
    print("=" * 70)

    todas_normas = {}
    normas_por_tema = defaultdict(list)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Buscar por cada tema
        for tema, terminos in TEMAS.items():
            print(f"\n{'=' * 50}")
            print(f"TEMA: {tema}")
            print(f"{'=' * 50}")

            for termino in terminos:
                print(f"\n  Buscando: '{termino}'")

                # Buscar en BCN
                resultados = await buscar_directo_bcn(termino, page)

                for r in resultados:
                    id_n = r['id_norma']
                    if id_n not in todas_normas:
                        todas_normas[id_n] = r
                        normas_por_tema[tema].append(id_n)
                        print(f"    + {r.get('tipo', '?')} {r.get('numero', '?')} (id: {id_n})")

                await asyncio.sleep(1)

        # Obtener detalles de normas encontradas
        print(f"\n{'=' * 50}")
        print("OBTENIENDO DETALLES DE NORMAS")
        print(f"{'=' * 50}")

        ids_a_detallar = list(todas_normas.keys())[:30]  # Limitar a 30

        for i, id_norma in enumerate(ids_a_detallar, 1):
            print(f"\n  [{i}/{len(ids_a_detallar)}] Detallando {id_norma}...")

            detalle = await explorar_norma_detalle(id_norma, page)

            if 'error' not in detalle:
                todas_normas[id_norma].update(detalle)
                print(f"    {detalle['tipo']} {detalle['numero']}: {detalle['temas']}")

            await asyncio.sleep(0.5)

        await browser.close()

    # Guardar resultados
    output = {
        'fecha': datetime.now().isoformat(),
        'temas_buscados': list(TEMAS.keys()),
        'total_normas': len(todas_normas),
        'normas_por_tema': {k: v for k, v in normas_por_tema.items()},
        'normas': list(todas_normas.values())
    }

    output_path = Path("data/busquedas/todos_temas_electricos.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Resumen
    print(f"\n{'=' * 70}")
    print("RESUMEN FINAL")
    print(f"{'=' * 70}")

    print(f"\nTotal normas: {len(todas_normas)}")

    print("\nPor tema buscado:")
    for tema, ids in normas_por_tema.items():
        print(f"  {tema}: {len(ids)} normas")

    print("\nPor tipo de norma:")
    por_tipo = defaultdict(int)
    for n in todas_normas.values():
        por_tipo[n.get('tipo', 'OTRO')] += 1
    for tipo, cnt in sorted(por_tipo.items(), key=lambda x: -x[1]):
        print(f"  {tipo}: {cnt}")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
