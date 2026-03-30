#!/usr/bin/env python3
"""
Descargar las 2 normas que existen pero estaban marcadas como errores.
"""

import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def obtener_info_norma(id_norma: str, page) -> dict:
    url = f'https://www.bcn.cl/leychile/navegar?idNorma={id_norma}'

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1.2)
        html = await page.content()

        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1).strip() if title_match else ''

        norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.I)
        tipo = norm_match.group(1).upper() if norm_match else 'DESCONOCIDO'
        if tipo == 'DTO': tipo = 'DECRETO'
        numero = norm_match.group(2) if norm_match else ''

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

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e)[:100], 'url': url}


async def main():
    ids = ['1037065', '187631']

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        nuevas = {}
        for id_norma in ids:
            print(f'Descargando {id_norma}...', end=' ')
            norma = await obtener_info_norma(id_norma, page)

            if 'error' not in norma:
                print(f'✓ {norma["tipo"]} {norma["numero"]}')
                nuevas[id_norma] = norma
            else:
                print(f'ERROR: {norma["error"]}')

            await asyncio.sleep(1)

        await browser.close()

    # Actualizar normas_completas.json
    with open('data/busquedas/normas_completas.json') as f:
        data = json.load(f)

    normas = {n['id_norma']: n for n in data['normas']}
    normas.update(nuevas)

    output = {
        'fecha': datetime.now().isoformat(),
        'total': len(normas),
        'normas': list(normas.values())
    }

    with open('data/busquedas/normas_completas.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Actualizar log_problemas - remover de errores
    with open('data/busquedas/log_problemas.json') as f:
        problemas = json.load(f)

    problemas['errores'] = [e for e in problemas['errores'] if e not in ids]

    with open('data/busquedas/log_problemas.json', 'w') as f:
        json.dump(problemas, f, indent=2)

    print(f'\nTotal normas ahora: {len(normas)}')
    print(f'Descargadas exitosas: {len(nuevas)}')
    print('Archivos actualizados.')


if __name__ == "__main__":
    asyncio.run(main())
