#!/usr/bin/env python3
"""
Verificar por qué no se pueden descargar las 124 restantes.
Intenta descargar una muestra y reporta los errores específicos.
"""

import asyncio
import json
import re
from pathlib import Path
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def verificar_norma(id_norma: str, page) -> dict:
    """Verificar si una norma existe y por qué no se puede descargar."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    resultado = {
        'id_norma': id_norma,
        'url': url,
        'accesible': False,
        'motivo': None,
        'status_code': None
    }

    try:
        response = await page.goto(url, wait_until='networkidle', timeout=20000)
        resultado['status_code'] = response.status

        await asyncio.sleep(1)
        html = await page.content()

        # Verificar si hay mensaje de error
        if 'no se encuentra' in html.lower() or 'no existe' in html.lower():
            resultado['motivo'] = 'NO_EXISTE'
        elif 'derogad' in html.lower():
            resultado['motivo'] = 'DEROGADA'
        elif 'sin texto' in html.lower():
            resultado['motivo'] = 'SIN_TEXTO'
        elif '<title>Ley Chile' in html and 'Biblioteca' in html:
            # Tiene formato válido
            title_match = re.search(r'<title>([^<]+)</title>', html)
            titulo = title_match.group(1) if title_match else ""

            # Intentar extraer tipo
            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION)', titulo, re.I)

            if norm_match:
                resultado['accesible'] = True
                resultado['motivo'] = 'EXISTE'
                resultado['titulo'] = titulo[:100]
            else:
                resultado['motivo'] = 'FORMATO_INVALIDO'
                resultado['titulo'] = titulo[:100]
        else:
            resultado['motivo'] = 'PAGINA_INVALIDA'

    except asyncio.TimeoutError:
        resultado['motivo'] = 'TIMEOUT'
    except Exception as e:
        resultado['motivo'] = f'ERROR: {str(e)[:50]}'

    return resultado


async def main():
    data = json.load(open("data/busquedas/normas_completas.json"))
    normas = {n['id_norma']: n for n in data['normas']}

    # Obtener pendientes
    pendientes = set()
    for n in normas.values():
        for v in n.get('vinculaciones_ids', []):
            if v not in normas and len(v) > 3:
                pendientes.add(v)

    pendientes = sorted(list(pendientes))

    print("=" * 70)
    print("VERIFICACIÓN DE NORMAS PENDIENTES")
    print("=" * 70)
    print(f"\nTotal pendientes: {len(pendientes)}")

    # Seleccionar muestra: primeras 20 + las últimas 10
    muestra = pendientes[:20] + pendientes[-10:]
    print(f"Verificando muestra de {len(muestra)} normas...\n")

    resultados = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, id_norma in enumerate(muestra, 1):
            print(f"[{i}/{len(muestra)}] Verificando {id_norma}...", end=" ")

            resultado = await verificar_norma(id_norma, page)
            resultados.append(resultado)

            print(f"{resultado['motivo']}")

            await asyncio.sleep(0.5)

        await browser.close()

    # Análisis de resultados
    print("\n" + "=" * 70)
    print("RESULTADOS")
    print("=" * 70)

    por_motivo = {}
    for r in resultados:
        motivo = r['motivo']
        if motivo not in por_motivo:
            por_motivo[motivo] = []
        por_motivo[motivo].append(r)

    print("\nDistribución de motivos:")
    for motivo, lista in sorted(por_motivo.items(), key=lambda x: -len(x[1])):
        print(f"  {motivo:20} : {len(lista)} normas ({len(lista)/len(resultados)*100:.1f}%)")

    # Mostrar ejemplos de cada tipo
    print("\n" + "-" * 70)
    print("EJEMPLOS POR MOTIVO")
    print("-" * 70)

    for motivo, lista in por_motivo.items():
        print(f"\n{motivo}:")
        for r in lista[:3]:
            print(f"  ID {r['id_norma']}: {r.get('titulo', 'N/A')[:60]}")

    # Guardar resultados
    output_path = Path("data/busquedas/verificacion_pendientes.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_pendientes': len(pendientes),
            'muestra_verificada': len(muestra),
            'resultados': resultados,
            'resumen': {m: len(l) for m, l in por_motivo.items()}
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResultados guardados en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
