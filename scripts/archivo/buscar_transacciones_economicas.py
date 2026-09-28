#!/usr/bin/env python3
"""
Buscar normas relacionadas a transacciones económicas en el mercado eléctrico.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# Términos de búsqueda para transacciones económicas
BUSQUEDAS = [
    # Transacciones y transferencias
    "transferencias energía eléctrica",
    "transacciones mercado eléctrico",
    "balance energía eléctrica",
    "costos marginales electricidad",

    # Precios y tarifas
    "precio nudo electricidad",
    "tarifas eléctricas",
    "peajes transmisión eléctrica",

    # Mercado spot
    "mercado spot eléctrico",
    "costo marginal energía",

    # Servicios complementarios
    "servicios complementarios eléctricos",
    "reserva frecuencia",

    # Pagos y liquidaciones
    "liquidación transferencias eléctricas",
    "pagos coordinador eléctrico",

    # Contratos
    "contratos suministro eléctrico",
    "licitaciones eléctricas",
]


async def buscar_en_bcn(query: str, page, max_results: int = 20) -> list:
    """Buscar un término en BCN y extraer resultados."""
    results = []

    # URL de búsqueda
    search_url = f"https://www.bcn.cl/leychile/buscar?b={query.replace(' ', '+')}"

    try:
        await page.goto(search_url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(2)

        # Extraer resultados de la búsqueda
        html = await page.content()

        # Buscar links a normas con idNorma
        # Patrón: href="...idNorma=XXXX">TITULO</a>
        pattern = r'href="[^"]*idNorma=(\d+)[^"]*"[^>]*>\s*([^<]+)</a>'
        matches = re.findall(pattern, html)

        seen = set()
        for match in matches[:max_results]:
            id_norma = match[0]
            titulo = match[1].strip()

            # Filtrar resultados relevantes (evitar navegación, etc.)
            if len(titulo) < 10 or id_norma in seen:
                continue
            if any(x in titulo.lower() for x in ['inicio', 'siguiente', 'anterior', 'página']):
                continue

            seen.add(id_norma)

            # Extraer tipo y número
            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s+(\d+)', titulo, re.IGNORECASE)
            if norm_match:
                tipo = norm_match.group(1).upper()
                if tipo == 'DTO':
                    tipo = 'DECRETO'
                numero = norm_match.group(2)

                results.append({
                    'id_norma': id_norma,
                    'tipo': tipo,
                    'numero': numero,
                    'titulo': titulo[:200],
                    'busqueda': query
                })

    except Exception as e:
        print(f"   Error buscando '{query}': {e}")

    return results


async def main():
    print("=" * 70)
    print("BUSCANDO NORMAS DE TRANSACCIONES ECONÓMICAS")
    print("=" * 70)

    todas_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, query in enumerate(BUSQUEDAS, 1):
            print(f"\n[{i}/{len(BUSQUEDAS)}] Buscando: '{query}'")

            resultados = await buscar_en_bcn(query, page)

            for r in resultados:
                key = r['id_norma']
                if key not in todas_normas:
                    todas_normas[key] = r
                    print(f"   + {r['tipo']} {r['numero']} (id: {r['id_norma']})")

            # Pausa entre búsquedas
            await asyncio.sleep(1)

        await browser.close()

    # Guardar resultados
    output = {
        'descripcion': 'Normas relacionadas a transacciones económicas en el mercado eléctrico',
        'busquedas_realizadas': BUSQUEDAS,
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
    print(f"\nGuardado en: {output_path}")

    # Mostrar por tipo
    por_tipo = {}
    for n in todas_normas.values():
        tipo = n['tipo']
        if tipo not in por_tipo:
            por_tipo[tipo] = []
        por_tipo[tipo].append(n)

    print("\nPor tipo:")
    for tipo, lista in sorted(por_tipo.items()):
        print(f"  {tipo}: {len(lista)}")
        for n in lista[:5]:
            print(f"    - {n['tipo']} {n['numero']}: {n['titulo'][:60]}...")
        if len(lista) > 5:
            print(f"    ... y {len(lista) - 5} más")

    return todas_normas


if __name__ == "__main__":
    asyncio.run(main())
