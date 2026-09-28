#!/usr/bin/env python3
"""
Buscar normas de transacciones económicas - usando búsqueda avanzada BCN.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# Términos de búsqueda
TERMINOS = [
    "transferencias de potencia",
    "precio nudo",
    "costo marginal",
    "peaje transmision",
    "servicios complementarios",
    "balance energia",
    "mercado electrico",
    "tarifas electricas",
    "licitacion electrica",
    "coordinador electrico",
]


async def buscar_bcn_avanzada(termino: str, page) -> list:
    """Buscar usando la interfaz avanzada de BCN."""
    results = []

    # URL de búsqueda con parámetros
    url = f"https://www.bcn.cl/leychile/consulta/buscador_normas?texto={termino.replace(' ', '%20')}&tipVigencia=0"

    try:
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)

        # Esperar a que carguen los resultados
        try:
            await page.wait_for_selector('a[href*="idNorma"]', timeout=10000)
        except:
            pass

        html = await page.content()

        # Buscar normas en los resultados
        # Patrón para links con idNorma
        pattern = r'href="[^"]*[?&]idNorma=(\d+)[^"]*"[^>]*>([^<]+)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)

        seen = set()
        for id_norma, titulo in matches:
            if id_norma in seen or len(titulo.strip()) < 5:
                continue

            titulo = titulo.strip()

            # Filtrar navegación
            if any(x in titulo.lower() for x in ['buscar', 'inicio', 'siguiente', 'anterior']):
                continue

            seen.add(id_norma)

            # Extraer tipo y número del título
            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|RES|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.IGNORECASE)

            if norm_match:
                tipo = norm_match.group(1).upper()
                if tipo == 'DTO':
                    tipo = 'DECRETO'
                elif tipo == 'RES':
                    tipo = 'RESOLUCION'
                numero = norm_match.group(2)

                results.append({
                    'id_norma': id_norma,
                    'tipo': tipo,
                    'numero': numero,
                    'titulo': titulo[:300],
                    'termino_busqueda': termino
                })

    except Exception as e:
        print(f"   Error: {e}")

    return results


async def buscar_por_materia(page) -> list:
    """Buscar normas por materia: Energía Eléctrica."""
    results = []

    # BCN tiene categorías por materia
    url = "https://www.bcn.cl/leychile/consulta/listado_n_sel?agr=1020&sub=910&tipCat=1"

    try:
        print("\n   Buscando por materia: Energía Eléctrica...")
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)

        html = await page.content()

        # Extraer normas
        pattern = r'idNorma=(\d+)[^"]*"[^>]*>\s*((?:LEY|DECRETO|DFL|DL|RESOLUCION|DTO)[^<]+)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)

        for id_norma, titulo in matches[:50]:  # Limitar a 50
            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.IGNORECASE)
            if norm_match:
                tipo = norm_match.group(1).upper()
                if tipo == 'DTO':
                    tipo = 'DECRETO'
                numero = norm_match.group(2)

                results.append({
                    'id_norma': id_norma,
                    'tipo': tipo,
                    'numero': numero,
                    'titulo': titulo.strip()[:200],
                    'termino_busqueda': 'materia:energia_electrica'
                })

    except Exception as e:
        print(f"   Error: {e}")

    return results


async def main():
    print("=" * 70)
    print("BUSCANDO NORMAS DE TRANSACCIONES ECONÓMICAS")
    print("Mercado Eléctrico Chileno")
    print("=" * 70)

    todas_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # 1. Buscar por términos
        for i, termino in enumerate(TERMINOS, 1):
            print(f"\n[{i}/{len(TERMINOS)}] Buscando: '{termino}'")

            resultados = await buscar_bcn_avanzada(termino, page)

            for r in resultados:
                key = r['id_norma']
                if key not in todas_normas:
                    todas_normas[key] = r
                    print(f"   + {r['tipo']} {r['numero']} (id: {key})")

            await asyncio.sleep(1.5)

        # 2. Buscar por materia
        print(f"\n[EXTRA] Buscando por materia...")
        resultados_materia = await buscar_por_materia(page)

        for r in resultados_materia:
            key = r['id_norma']
            if key not in todas_normas:
                todas_normas[key] = r
                print(f"   + {r['tipo']} {r['numero']} (id: {key})")

        await browser.close()

    # Guardar resultados
    output = {
        'descripcion': 'Normas relacionadas a transacciones económicas en el mercado eléctrico',
        'terminos_busqueda': TERMINOS,
        'fecha_busqueda': datetime.now().isoformat(),
        'total': len(todas_normas),
        'normas': list(todas_normas.values())
    }

    output_path = Path("data/busquedas/transacciones_economicas.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"RESUMEN: {len(todas_normas)} normas únicas encontradas")
    print(f"{'=' * 70}")

    # Mostrar por tipo
    por_tipo = {}
    for n in todas_normas.values():
        tipo = n['tipo']
        if tipo not in por_tipo:
            por_tipo[tipo] = []
        por_tipo[tipo].append(n)

    print("\nPor tipo:")
    for tipo, lista in sorted(por_tipo.items()):
        print(f"\n  {tipo} ({len(lista)}):")
        for n in lista[:8]:
            print(f"    - N° {n['numero']} (id: {n['id_norma']})")
        if len(lista) > 8:
            print(f"    ... y {len(lista) - 8} más")

    print(f"\nGuardado en: {output_path}")

    return todas_normas


if __name__ == "__main__":
    asyncio.run(main())
