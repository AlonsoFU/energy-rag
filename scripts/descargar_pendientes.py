#!/usr/bin/env python3
"""
Descargar vinculaciones pendientes.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def obtener_info_norma(id_norma: str, page) -> dict:
    """Obtener información de una norma de BCN."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=25000)
        await asyncio.sleep(1)

        html = await page.content()

        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1).strip() if title_match else ""

        norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.I)
        if norm_match:
            tipo = norm_match.group(1).upper()
            if tipo == 'DTO': tipo = 'DECRETO'
            numero = norm_match.group(2)
        else:
            tipo = "DESCONOCIDO"
            numero = ""

        org_match = re.search(r'MINISTERIO\s+DE\s+[A-ZÁÉÍÓÚ]+(?:\s+[A-ZÁÉÍÓÚ,]+)*', html, re.I)
        organismo = org_match.group(0)[:50] if org_match else ""

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

        vinculaciones = []
        vinc_pattern = r'<a[^>]*href="[^"]*idNorma=(\d+)[^"]*"[^>]*>'
        for match in re.finditer(vinc_pattern, html, re.I):
            vinc_id = match.group(1)
            if vinc_id != id_norma and len(vinc_id) > 3:
                vinculaciones.append(vinc_id)
        vinculaciones = list(set(vinculaciones))

        return {
            'id_norma': id_norma,
            'tipo': tipo,
            'numero': numero,
            'titulo': titulo[:200],
            'organismo': organismo,
            'temas_detectados': temas,
            'vinculaciones_ids': vinculaciones[:15],
            'url': url
        }

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e)[:50], 'url': url}


async def main():
    print("=" * 60)
    print("DESCARGA DE VINCULACIONES PENDIENTES")
    print("=" * 60)

    # Cargar normas existentes
    data = json.load(open("data/busquedas/normas_completas.json"))
    normas = {n['id_norma']: n for n in data['normas']}
    ids_existentes = set(normas.keys())

    # Encontrar pendientes
    pendientes = set()
    for n in normas.values():
        for v_id in n.get('vinculaciones_ids', []):
            if v_id not in ids_existentes and len(v_id) > 3:
                pendientes.add(v_id)

    print(f"\nNormas existentes: {len(ids_existentes)}")
    print(f"Pendientes a descargar: {len(pendientes)}")

    nuevas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, id_norma in enumerate(sorted(pendientes), 1):
            print(f"[{i}/{len(pendientes)}] {id_norma}...", end=" ")

            norma = await obtener_info_norma(id_norma, page)

            if 'error' not in norma:
                print(f"✓ {norma['tipo']} {norma['numero']}")
                nuevas[id_norma] = norma
            else:
                print(f"✗ {norma.get('error', '')[:30]}")

            await asyncio.sleep(0.8)

        await browser.close()

    # Combinar
    normas.update(nuevas)

    # Guardar
    output = {
        'fecha': datetime.now().isoformat(),
        'total': len(normas),
        'normas': list(normas.values())
    }

    with open("data/busquedas/normas_completas.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 60}")
    print(f"Total normas ahora: {len(normas)}")
    print(f"Nuevas descargadas: {len(nuevas)}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
