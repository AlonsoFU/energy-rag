#!/usr/bin/env python3
"""
Descargar las últimas 203 normas pendientes.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def obtener_info_norma(id_norma: str, page) -> dict:
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
    try:
        await page.goto(url, wait_until='networkidle', timeout=20000)
        await asyncio.sleep(0.8)
        html = await page.content()

        title_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = title_match.group(1).strip() if title_match else ""

        norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO)\s*N?[°º]?\s*(\d+)', titulo, re.I)
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
    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e)[:100], 'url': url}


async def descargar_lote(ids_lote, num_lote):
    print(f"\n[Lote {num_lote}] Descargando {len(ids_lote)} normas...")
    nuevas = {}
    errores = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for i, id_norma in enumerate(ids_lote, 1):
            norma = await obtener_info_norma(id_norma, page)
            if 'error' not in norma:
                print(f"  [{i}/{len(ids_lote)}] ✓ {norma['tipo']} {norma['numero']}")
                nuevas[id_norma] = norma
            else:
                print(f"  [{i}/{len(ids_lote)}] ✗ {id_norma} - {norma.get('error', '')[:30]}")
                errores.append(id_norma)
            await asyncio.sleep(0.5)

        await browser.close()

    print(f"  → Exitosas: {len(nuevas)}, Errores: {len(errores)}")
    return nuevas, errores


async def main():
    data = json.load(open("data/busquedas/normas_completas.json"))
    normas = {n['id_norma']: n for n in data['normas']}

    # Calcular pendientes
    pendientes = set()
    for n in normas.values():
        for v in n.get('vinculaciones_ids', []):
            if v not in normas and len(v) > 3:
                pendientes.add(v)

    pendientes = sorted(list(pendientes))
    print(f"Normas actuales: {len(normas)}")
    print(f"Pendientes: {len(pendientes)}")

    # Dividir en lotes de 50
    lotes = [pendientes[i:i+50] for i in range(0, len(pendientes), 50)]

    todos_errores = []
    for num, lote in enumerate(lotes, 1):
        nuevas, errores = await descargar_lote(lote, num)
        todos_errores.extend(errores)
        normas.update(nuevas)

        # Guardar después de cada lote
        output = {
            'fecha': datetime.now().isoformat(),
            'total': len(normas),
            'normas': list(normas.values())
        }
        with open("data/busquedas/normas_completas.json", 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"  Guardado. Total acumulado: {len(normas)}")

    print(f"\n{'='*60}")
    print(f"DESCARGA FINAL COMPLETADA")
    print(f"{'='*60}")
    print(f"Total normas: {len(normas)}")
    print(f"Errores: {len(todos_errores)}")

    if todos_errores:
        print(f"\nIDs con error:")
        print(f"  {todos_errores[:20]}...")

        # Guardar errores
        with open("data/busquedas/errores_descarga.json", 'w') as f:
            json.dump({'errores': todos_errores, 'total': len(todos_errores)}, f, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
