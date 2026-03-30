#!/usr/bin/env python3
"""
Descargar normas de BCN usando IDs conocidos obtenidos de WebSearch.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# IDs conocidos por tema (obtenidos de búsquedas web)
IDS_POR_TEMA = {
    "DISTRIBUCION_VAD": {
        "descripcion": "Valor Agregado de Distribución y tarifas de distribución",
        "ids": [
            "1146553",   # Decreto 10 (2020) - Valorización transmisión
            "1149788",   # Decreto 57 (2020) - Distribución
            "1074277",   # Ley 20805
        ]
    },
    "PEAJES_TRANSMISION": {
        "descripcion": "Peajes y remuneración de transmisión",
        "ids": [
            "1122953",   # Decreto 4T (2018)
            "1160108",   # Decreto 37 (2021)
            "1204465",   # Decreto 13 (2024)
            "1207690",   # Decreto 262 (2024)
            "1143069",   # Decreto 8 (2020)
        ]
    },
    "SERVICIOS_COMPLEMENTARIOS": {
        "descripcion": "Servicios complementarios y control de frecuencia",
        "ids": [
            "1129970",   # Decreto 113 (2019)
            "1113260",   # Decreto 44 (2018)
            "1047565",   # Decreto 130 (2012)
        ]
    },
    "MEDICION": {
        "descripcion": "Medidores y sistemas de medición",
        "ids": [
            "202975",    # Decreto 3386 (1935) - Normas medidores
        ]
    },
    "BASE_LEGAL": {
        "descripcion": "Leyes base del sector eléctrico",
        "ids": [
            "258171",    # DFL 4/20.018 - LGSE refundido
        ]
    }
}


async def obtener_info_norma(id_norma: str, page) -> dict:
    """Obtener información completa de una norma de BCN."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        html = await page.content()

        # Título de la página
        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1).strip() if title_match else ""

        # Extraer tipo y número
        norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.I)
        if norm_match:
            tipo = norm_match.group(1).upper()
            if tipo == 'DTO': tipo = 'DECRETO'
            numero = norm_match.group(2)
        else:
            tipo = "DESCONOCIDO"
            numero = ""

        # Buscar fecha de publicación
        fecha_pub = ""
        fecha_match = re.search(r'Fecha publicaci[oó]n[:\s]*(\d{2}[/-]\w{3}[/-]\d{4}|\d{2}[/-]\d{2}[/-]\d{4})', html, re.I)
        if fecha_match:
            fecha_pub = fecha_match.group(1)

        # Buscar organismo
        org_match = re.search(r'MINISTERIO\s+DE\s+[A-ZÁÉÍÓÚ]+(?:\s+[A-ZÁÉÍÓÚ]+)?', html, re.I)
        organismo = org_match.group(0) if org_match else ""

        # Detectar temas en contenido
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
        if 'coordinador' in texto_lower: temas.append('COORDINADOR')

        # Extraer vinculaciones (modificaciones)
        vinculaciones = []
        vinc_pattern = r'<a[^>]*href="[^"]*idNorma=(\d+)[^"]*"[^>]*>\s*(DTO|Decreto|Ley|DFL|DL|RES)[^<]*</a>'
        for match in re.finditer(vinc_pattern, html, re.I):
            vinc_id = match.group(1)
            if vinc_id != id_norma:
                vinculaciones.append(vinc_id)
        vinculaciones = list(set(vinculaciones))

        return {
            'id_norma': id_norma,
            'tipo': tipo,
            'numero': numero,
            'titulo': titulo[:200],
            'fecha_publicacion': fecha_pub,
            'organismo': organismo,
            'temas_detectados': temas,
            'num_vinculaciones': len(vinculaciones),
            'vinculaciones_ids': vinculaciones[:10],
            'url': url
        }

    except Exception as e:
        return {
            'id_norma': id_norma,
            'error': str(e),
            'url': url
        }


async def main():
    print("=" * 70)
    print("DESCARGA DE NORMAS - IDs CONOCIDOS")
    print("=" * 70)

    resultados = {}
    normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for tema, info in IDS_POR_TEMA.items():
            print(f"\n{'─' * 50}")
            print(f"TEMA: {tema}")
            print(f"  {info['descripcion']}")
            print(f"{'─' * 50}")

            resultados[tema] = {
                'descripcion': info['descripcion'],
                'normas': []
            }

            for id_norma in info['ids']:
                print(f"\n  Descargando {id_norma}...")

                norma = await obtener_info_norma(id_norma, page)

                if 'error' not in norma:
                    print(f"    ✓ {norma['tipo']} {norma['numero']}: {norma['temas_detectados']}")
                    resultados[tema]['normas'].append(norma)
                    normas[id_norma] = norma
                else:
                    print(f"    ✗ Error: {norma['error'][:50]}")

                await asyncio.sleep(1)

        await browser.close()

    # Guardar
    output = {
        'fecha': datetime.now().isoformat(),
        'por_tema': resultados,
        'total': len(normas),
        'normas': list(normas.values())
    }

    output_path = Path("data/busquedas/normas_ids_conocidos.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Resumen
    print(f"\n{'=' * 70}")
    print("RESUMEN")
    print(f"{'=' * 70}")

    print(f"\nTotal normas descargadas: {len(normas)}")

    print("\nPor tema:")
    for tema, info in resultados.items():
        cnt = len(info['normas'])
        print(f"  {tema}: {cnt} normas")
        for n in info['normas']:
            print(f"    - {n['tipo']} {n['numero']} (id: {n['id_norma']})")

    # Todos los temas detectados
    print("\nTemas detectados en contenido:")
    todos_temas = {}
    for n in normas.values():
        for t in n.get('temas_detectados', []):
            if t not in todos_temas:
                todos_temas[t] = []
            todos_temas[t].append(f"{n['tipo']} {n['numero']}")

    for tema, lista in sorted(todos_temas.items(), key=lambda x: -len(x[1])):
        print(f"  {tema} ({len(lista)}): {', '.join(lista[:5])}")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
