#!/usr/bin/env python3
"""
Buscar normas de transacciones económicas - interacción directa con BCN.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


TERMINOS = [
    "transferencias potencia",
    "precio nudo",
    "costo marginal",
    "servicios complementarios",
    "coordinador electrico",
    "peaje transmision",
    "mercado electrico",
    "balance energia",
]


async def buscar_con_formulario(termino: str, page) -> list:
    """Buscar usando el formulario de BCN."""
    results = []

    try:
        # Ir a la página de búsqueda
        await page.goto("https://www.bcn.cl/leychile", wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)

        # Buscar el campo de búsqueda
        search_input = await page.query_selector('input[type="search"], input[name*="busca"], input[id*="busca"], input[placeholder*="Buscar"]')

        if search_input:
            # Limpiar y escribir término
            await search_input.fill('')
            await search_input.fill(termino)
            await asyncio.sleep(0.5)

            # Presionar Enter o buscar botón
            await search_input.press('Enter')
            await asyncio.sleep(3)

            # Esperar resultados
            try:
                await page.wait_for_selector('a[href*="idNorma"]', timeout=10000)
            except:
                pass

            html = await page.content()

            # Extraer normas
            pattern = r'idNorma=(\d+)[^"]*"[^>]*>\s*([^<]{10,200})</a>'
            matches = re.findall(pattern, html, re.IGNORECASE)

            seen = set()
            for id_norma, titulo in matches:
                if id_norma in seen:
                    continue
                titulo = titulo.strip()
                if len(titulo) < 10:
                    continue
                if any(x in titulo.lower() for x in ['inicio', 'buscar', 'siguiente']):
                    continue

                seen.add(id_norma)

                norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|RES|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.IGNORECASE)
                if norm_match:
                    tipo = norm_match.group(1).upper()
                    if tipo == 'DTO':
                        tipo = 'DECRETO'
                    elif tipo == 'RES':
                        tipo = 'RESOLUCION'

                    results.append({
                        'id_norma': id_norma,
                        'tipo': tipo,
                        'numero': norm_match.group(2),
                        'titulo': titulo[:200],
                        'termino': termino
                    })

    except Exception as e:
        print(f"   Error: {e}")

    return results


async def explorar_desde_norma_conocida(page) -> list:
    """
    Partir desde normas conocidas y explorar sus referencias.
    Conocemos D.62 (potencia), DFL 4 (LGSE), etc.
    """
    results = []

    normas_semilla = [
        ("250604", "Decreto 62 - Potencia"),
        ("258171", "DFL 4 - LGSE"),
        ("1109624", "Ley 20936 - Transmisión"),
        ("1112591", "Resolución 711 - NTSyCS"),
    ]

    for id_norma, desc in normas_semilla:
        print(f"\n   Explorando referencias desde: {desc}")

        url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)

        html = await page.content()

        # Buscar todas las normas referenciadas
        pattern = r'idNorma=(\d+)[^"]*"[^>]*>\s*((?:LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RES)[^<]{5,150})</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)

        seen = set()
        for ref_id, titulo in matches:
            if ref_id in seen or ref_id == id_norma:
                continue

            seen.add(ref_id)

            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RES)\s*N?[°º]?\s*(\d+)', titulo, re.IGNORECASE)
            if norm_match:
                tipo = norm_match.group(1).upper()
                if tipo == 'DTO':
                    tipo = 'DECRETO'
                elif tipo == 'RES':
                    tipo = 'RESOLUCION'

                results.append({
                    'id_norma': ref_id,
                    'tipo': tipo,
                    'numero': norm_match.group(2),
                    'titulo': titulo.strip()[:150],
                    'encontrado_desde': desc
                })
                print(f"      + {tipo} {norm_match.group(2)} (id: {ref_id})")

    return results


async def main():
    print("=" * 70)
    print("BUSCANDO NORMAS DE TRANSACCIONES ECONÓMICAS")
    print("Estrategia: Explorar desde normas conocidas")
    print("=" * 70)

    todas_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Estrategia 1: Explorar desde normas conocidas
        print("\n[1] Explorando desde normas conocidas...")
        resultados = await explorar_desde_norma_conocida(page)

        for r in resultados:
            key = r['id_norma']
            if key not in todas_normas:
                todas_normas[key] = r

        # Estrategia 2: Buscar con formulario
        print("\n[2] Buscando con términos específicos...")
        for termino in TERMINOS[:5]:  # Solo primeros 5 para no demorar
            print(f"\n   Buscando: '{termino}'")
            resultados = await buscar_con_formulario(termino, page)

            for r in resultados:
                key = r['id_norma']
                if key not in todas_normas:
                    todas_normas[key] = r
                    print(f"      + {r['tipo']} {r['numero']} (id: {key})")

            await asyncio.sleep(1)

        await browser.close()

    # Guardar resultados
    output = {
        'descripcion': 'Normas relacionadas a transacciones económicas en el mercado eléctrico',
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

    # Clasificar por tipo
    por_tipo = {}
    for n in todas_normas.values():
        tipo = n['tipo']
        if tipo not in por_tipo:
            por_tipo[tipo] = []
        por_tipo[tipo].append(n)

    for tipo in sorted(por_tipo.keys()):
        print(f"\n{tipo} ({len(por_tipo[tipo])}):")
        for n in por_tipo[tipo][:10]:
            print(f"  - N° {n['numero']} (id: {n['id_norma']}): {n.get('titulo', '')[:50]}...")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
