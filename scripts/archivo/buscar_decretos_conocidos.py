#!/usr/bin/env python3
"""
Buscar decretos conocidos del sector eléctrico por tema.
Basado en conocimiento del marco regulatorio chileno.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


# Decretos conocidos del sector eléctrico por tema
DECRETOS_POR_TEMA = {
    "TRANSFERENCIAS_POTENCIA": {
        "descripcion": "Transferencias de potencia entre generadores",
        "normas": [
            {"nombre": "Decreto 62", "buscar": "Decreto 62 transferencias potencia"},
            {"nombre": "Decreto 44", "buscar": "Decreto 44 modifica 62"},
            {"nombre": "Decreto 42", "buscar": "Decreto 42 modifica 62 2020"},
            {"nombre": "Decreto 70", "buscar": "Decreto 70 modifica 62 2024"},
        ]
    },
    "TRANSFERENCIAS_ENERGIA": {
        "descripcion": "Balance y transferencias de energía",
        "normas": [
            {"nombre": "DS 291", "buscar": "Decreto 291 energia"},
            {"nombre": "DS 244", "buscar": "Decreto 244 balance energia"},
        ]
    },
    "PEAJES_TRANSMISION": {
        "descripcion": "Peajes y remuneración de transmisión",
        "normas": [
            {"nombre": "Decreto 14", "buscar": "Decreto 14 transmision 2019"},
            {"nombre": "Decreto 37", "buscar": "Decreto 37 peajes transmision"},
            {"nombre": "Decreto 4", "buscar": "Decreto 4 reglamento transmision 2018"},
            {"nombre": "Decreto 130", "buscar": "Decreto 130 remuneracion transmision"},
        ]
    },
    "SERVICIOS_COMPLEMENTARIOS": {
        "descripcion": "Servicios complementarios y control de frecuencia",
        "normas": [
            {"nombre": "DS 113", "buscar": "Decreto 113 servicios complementarios"},
            {"nombre": "DS 125", "buscar": "Decreto 125 servicios complementarios"},
            {"nombre": "NTSyCS", "buscar": "norma tecnica seguridad calidad servicio"},
        ]
    },
    "DISTRIBUCION": {
        "descripcion": "Tarifas y regulación de distribución",
        "normas": [
            {"nombre": "DS 11", "buscar": "Decreto 11 tarifas distribucion"},
            {"nombre": "DS 15", "buscar": "Decreto 15 distribucion electrica"},
            {"nombre": "DS 8", "buscar": "Decreto 8 valor agregado distribucion"},
        ]
    },
    "MEDICION": {
        "descripcion": "Medidores y sistemas de medición",
        "normas": [
            {"nombre": "DS 18", "buscar": "Decreto 18 medidores electricos"},
            {"nombre": "DS 119", "buscar": "Decreto 119 medicion"},
            {"nombre": "Res CNE", "buscar": "Resolucion CNE medidores inteligentes"},
        ]
    },
    "COORDINADOR": {
        "descripcion": "Reglamento del Coordinador Eléctrico Nacional",
        "normas": [
            {"nombre": "Decreto 52", "buscar": "Decreto 52 coordinador electrico 2024"},
            {"nombre": "Decreto 6", "buscar": "Decreto 6 coordinador electrico"},
        ]
    },
    "PRECIO_NUDO": {
        "descripcion": "Fijación de precios de nudo",
        "normas": [
            {"nombre": "DS 327", "buscar": "Decreto 327 reglamento LGSE"},
            {"nombre": "DS 120", "buscar": "Decreto 120 precio nudo"},
        ]
    }
}


async def buscar_norma_bcn(busqueda: str, page) -> dict:
    """Buscar una norma específica en BCN."""
    url = f"https://www.bcn.cl/leychile/consulta/buscador_normas?texto={busqueda.replace(' ', '%20')}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(2)

        html = await page.content()

        # Buscar primer resultado con idNorma
        match = re.search(r'idNorma=(\d+)[^"]*"[^>]*>\s*([^<]+)', html)
        if match:
            id_norma = match.group(1)
            titulo = match.group(2).strip()

            # Extraer tipo y número
            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RES)\s*N?[°º]?\s*(\d+)', titulo, re.I)
            if norm_match:
                tipo = norm_match.group(1).upper()
                if tipo == 'DTO': tipo = 'DECRETO'
                if tipo == 'RES': tipo = 'RESOLUCION'

                return {
                    'id_norma': id_norma,
                    'tipo': tipo,
                    'numero': norm_match.group(2),
                    'titulo': titulo[:150],
                    'busqueda': busqueda
                }

    except Exception as e:
        pass

    return None


async def obtener_info_norma(id_norma: str, page) -> dict:
    """Obtener información detallada de una norma."""
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

        # Referencias (otros idNorma en la página)
        refs = set(re.findall(r'idNorma=(\d+)', html))
        refs.discard(id_norma)

        # Temas detectados
        texto = html.lower()
        temas = []
        if 'distribuci' in texto: temas.append('DISTRIBUCION')
        if 'transmisi' in texto: temas.append('TRANSMISION')
        if 'peaje' in texto: temas.append('PEAJES')
        if 'complementari' in texto: temas.append('SSCC')
        if 'medid' in texto: temas.append('MEDICION')
        if 'potencia' in texto: temas.append('POTENCIA')
        if 'tarifa' in texto: temas.append('TARIFAS')

        return {
            'id_norma': id_norma,
            'tipo': tipo,
            'numero': numero,
            'titulo': titulo[:150],
            'num_referencias': len(refs),
            'temas_detectados': temas
        }

    except:
        return {'id_norma': id_norma, 'error': True}


async def main():
    print("=" * 70)
    print("BÚSQUEDA DE DECRETOS DEL SECTOR ELÉCTRICO")
    print("=" * 70)

    resultados = {}
    normas_encontradas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for tema, info in DECRETOS_POR_TEMA.items():
            print(f"\n{'─' * 50}")
            print(f"TEMA: {tema}")
            print(f"  {info['descripcion']}")
            print(f"{'─' * 50}")

            resultados[tema] = {
                'descripcion': info['descripcion'],
                'normas': []
            }

            for norma in info['normas']:
                print(f"\n  Buscando: {norma['nombre']}")

                result = await buscar_norma_bcn(norma['buscar'], page)

                if result:
                    print(f"    ✓ Encontrado: {result['tipo']} {result['numero']} (id: {result['id_norma']})")
                    resultados[tema]['normas'].append(result)
                    normas_encontradas[result['id_norma']] = result
                else:
                    print(f"    ✗ No encontrado")

                await asyncio.sleep(1)

        # Obtener detalles de cada norma encontrada
        print(f"\n{'=' * 70}")
        print("OBTENIENDO DETALLES")
        print(f"{'=' * 70}")

        for id_norma in list(normas_encontradas.keys())[:25]:
            info = await obtener_info_norma(id_norma, page)
            if 'error' not in info:
                normas_encontradas[id_norma].update(info)
                print(f"  {info['tipo']} {info['numero']}: {info['temas_detectados']}")
            await asyncio.sleep(0.5)

        await browser.close()

    # Guardar
    output = {
        'fecha': datetime.now().isoformat(),
        'por_tema': resultados,
        'total': len(normas_encontradas),
        'normas': list(normas_encontradas.values())
    }

    output_path = Path("data/busquedas/decretos_sector_electrico.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Resumen
    print(f"\n{'=' * 70}")
    print("RESUMEN")
    print(f"{'=' * 70}")

    for tema, info in resultados.items():
        normas = info['normas']
        print(f"\n{tema} ({len(normas)} normas):")
        for n in normas:
            print(f"  - {n['tipo']} {n['numero']} (id: {n['id_norma']})")

    print(f"\nTotal: {len(normas_encontradas)} normas")
    print(f"Guardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
