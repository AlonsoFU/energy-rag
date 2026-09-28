#!/usr/bin/env python3
"""
Descargar las últimas 43 normas pendientes (excluyendo problemáticas conocidas).
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def obtener_info_norma(id_norma: str, page, reintentos=3) -> dict:
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    for intento in range(reintentos):
        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(1.2)
            html = await page.content()

            # Verificar si está derogada o no existe
            if 'derogad' in html.lower():
                return {'id_norma': id_norma, 'derogada': True, 'url': url}
            if 'no se encuentra' in html.lower() or 'no existe' in html.lower():
                return {'id_norma': id_norma, 'no_existe': True, 'url': url}

            title_match = re.search(r'<title>([^<]+)</title>', html)
            titulo = title_match.group(1).strip() if title_match else ""

            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RECTIFICACION)\s*N?[°º]?\s*(\d+)', titulo, re.I)
            tipo = norm_match.group(1).upper() if norm_match else "DESCONOCIDO"
            if tipo == 'DTO': tipo = 'DECRETO'
            numero = norm_match.group(2) if norm_match else ""

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
            if 'transferencia' in texto_lower: temas.append('TRANSFERENCIAS')

            vinculaciones = list(set(re.findall(r'idNorma=(\d{4,})', html)))
            vinculaciones = [v for v in vinculaciones if v != id_norma][:15]

            return {
                'id_norma': id_norma, 'tipo': tipo, 'numero': numero,
                'titulo': titulo[:200], 'temas_detectados': temas,
                'vinculaciones_ids': vinculaciones, 'url': url
            }

        except asyncio.TimeoutError:
            if intento < reintentos - 1:
                print(f"    Timeout en {id_norma}, reintentando ({intento+1}/{reintentos})...")
                await asyncio.sleep(3)
                continue
            return {'id_norma': id_norma, 'error': 'Timeout', 'url': url}
        except Exception as e:
            if intento < reintentos - 1:
                await asyncio.sleep(3)
                continue
            return {'id_norma': id_norma, 'error': str(e)[:100], 'url': url}

    return {'id_norma': id_norma, 'error': 'Max reintentos', 'url': url}


async def main():
    # Cargar datos actuales
    data = json.load(open("data/busquedas/normas_completas.json"))
    normas = {n['id_norma']: n for n in data['normas']}

    # Cargar problemas conocidos
    with open("data/busquedas/log_problemas.json") as f:
        problemas = json.load(f)

    problematicas = set(problemas['derogadas'] + problemas['no_existen'] + problemas['errores'])

    # Calcular pendientes descargables
    pendientes = set()
    for n in normas.values():
        for v in n.get('vinculaciones_ids', []):
            if v not in normas and len(v) > 3:
                pendientes.add(v)

    pendientes_descargables = sorted(list(pendientes - problematicas))

    print(f"Normas actuales: {len(normas)}")
    print(f"Pendientes descargables: {len(pendientes_descargables)}\n")

    # Descargar
    nuevas = {}
    nuevas_derogadas = []
    nuevas_no_existen = []
    nuevas_errores = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, id_norma in enumerate(pendientes_descargables, 1):
            print(f"[{i}/{len(pendientes_descargables)}] {id_norma}...", end=" ")

            norma = await obtener_info_norma(id_norma, page)

            if norma.get('derogada'):
                print("DEROGADA")
                nuevas_derogadas.append(id_norma)
            elif norma.get('no_existe'):
                print("NO_EXISTE")
                nuevas_no_existen.append(id_norma)
            elif 'error' in norma:
                print(f"ERROR: {norma['error'][:30]}")
                nuevas_errores.append(id_norma)
            else:
                print(f"✓ {norma['tipo']} {norma['numero']}")
                nuevas[id_norma] = norma

            await asyncio.sleep(0.8)

        await browser.close()

    print(f"\n{'='*70}")
    print(f"DESCARGA COMPLETA")
    print(f"{'='*70}")
    print(f"Exitosas: {len(nuevas)}")
    print(f"Derogadas: {len(nuevas_derogadas)}")
    print(f"No existen: {len(nuevas_no_existen)}")
    print(f"Errores: {len(nuevas_errores)}")

    # Actualizar normas_completas.json
    normas.update(nuevas)
    output = {
        'fecha': datetime.now().isoformat(),
        'total': len(normas),
        'normas': list(normas.values())
    }
    with open("data/busquedas/normas_completas.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Actualizar log_problemas.json
    problemas['derogadas'].extend(nuevas_derogadas)
    problemas['no_existen'].extend(nuevas_no_existen)
    problemas['errores'].extend(nuevas_errores)

    with open("data/busquedas/log_problemas.json", 'w') as f:
        json.dump(problemas, f, indent=2)

    print(f"\nTotal normas ahora: {len(normas)}")
    print(f"Archivos actualizados:")
    print(f"  - data/busquedas/normas_completas.json")
    print(f"  - data/busquedas/log_problemas.json")


if __name__ == "__main__":
    asyncio.run(main())
