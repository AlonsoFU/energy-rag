#!/usr/bin/env python3
"""
Verificar manualmente las pendientes para demostrar que fallan.
"""

import asyncio
import json
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def verificar_norma(id_norma: str, page) -> dict:
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1)
        html = await page.content()

        # Extraer título
        import re
        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1).strip() if title_match else ""

        # Verificar estado
        html_lower = html.lower()

        if 'derogad' in html_lower:
            return {'id': id_norma, 'estado': 'DEROGADA', 'titulo': titulo, 'url': url}

        if 'no se encuentra' in html_lower or 'no existe' in html_lower or 'no hay información' in html_lower:
            return {'id': id_norma, 'estado': 'NO_EXISTE', 'titulo': titulo, 'url': url}

        # Si llegamos aquí, existe
        return {'id': id_norma, 'estado': 'EXISTE', 'titulo': titulo, 'url': url}

    except Exception as e:
        return {'id': id_norma, 'estado': 'ERROR', 'error': str(e)[:100], 'url': url}


async def main():
    # Cargar pendientes
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}

    pendientes = set()
    for n in normas.values():
        for v in n.get('vinculaciones_ids', []):
            if v not in normas and len(v) > 3:
                pendientes.add(v)

    pendientes = sorted(list(pendientes))

    print(f"Verificando {len(pendientes)} normas pendientes...\n")

    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, id_norma in enumerate(pendientes, 1):
            print(f"[{i}/{len(pendientes)}] {id_norma}...", end=" ")

            resultado = await verificar_norma(id_norma, page)
            resultados.append(resultado)

            print(f"{resultado['estado']}")
            if resultado['estado'] == 'EXISTE':
                print(f"     ⚠️  ENCONTRADA: {resultado['titulo'][:60]}")

            await asyncio.sleep(0.8)

        await browser.close()

    # Resumen
    print(f"\n{'='*70}")
    print("RESUMEN DE VERIFICACIÓN")
    print(f"{'='*70}")

    estados = {}
    for r in resultados:
        estados[r['estado']] = estados.get(r['estado'], 0) + 1

    for estado, count in sorted(estados.items()):
        print(f"{estado:12} {count:3}")

    # Mostrar las que existen
    existen = [r for r in resultados if r['estado'] == 'EXISTE']
    if existen:
        print(f"\n⚠️  NORMAS QUE EXISTEN Y DEBERÍAN DESCARGARSE ({len(existen)}):")
        for r in existen:
            print(f"  - {r['id']}: {r['titulo'][:80]}")
            print(f"    URL: {r['url']}")

    # Guardar resultados
    with open('data/busquedas/verificacion_pendientes_manual.json', 'w', encoding='utf-8') as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\nResultados guardados: data/busquedas/verificacion_pendientes_manual.json")


if __name__ == "__main__":
    asyncio.run(main())
