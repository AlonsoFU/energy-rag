#!/usr/bin/env python3
"""
Descargar normas referenciadas (vinculaciones) de las normas ya descargadas.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def obtener_info_norma(id_norma: str, page) -> dict:
    """Obtener información completa de una norma de BCN."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1.5)

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

        # Buscar organismo
        org_match = re.search(r'MINISTERIO\s+DE\s+[A-ZÁÉÍÓÚ]+(?:\s+[A-ZÁÉÍÓÚ,]+)*', html, re.I)
        organismo = org_match.group(0)[:50] if org_match else ""

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
        if 'transferencia' in texto_lower: temas.append('TRANSFERENCIAS')

        # Extraer vinculaciones (otras normas referenciadas)
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
            'num_vinculaciones': len(vinculaciones),
            'vinculaciones_ids': vinculaciones[:15],
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
    print("DESCARGA DE NORMAS REFERENCIADAS (VINCULACIONES)")
    print("=" * 70)

    # Cargar normas ya descargadas
    input_path = Path("data/busquedas/normas_ids_conocidos.json")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Recolectar todos los IDs de vinculaciones
    ids_existentes = set(n['id_norma'] for n in data['normas'])
    ids_vinculaciones = set()

    for norma in data['normas']:
        for v_id in norma.get('vinculaciones_ids', []):
            if v_id not in ids_existentes and len(v_id) > 3:
                ids_vinculaciones.add(v_id)

    print(f"\nNormas ya descargadas: {len(ids_existentes)}")
    print(f"IDs de vinculaciones a descargar: {len(ids_vinculaciones)}")
    print(f"IDs: {sorted(ids_vinculaciones)[:20]}...")

    nuevas_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Descargar cada vinculación (máximo 30)
        for i, id_norma in enumerate(list(ids_vinculaciones)[:30], 1):
            print(f"\n[{i}/{min(30, len(ids_vinculaciones))}] Descargando {id_norma}...")

            norma = await obtener_info_norma(id_norma, page)

            if 'error' not in norma:
                print(f"    ✓ {norma['tipo']} {norma['numero']}: {norma['temas_detectados']}")
                nuevas_normas[id_norma] = norma
            else:
                print(f"    ✗ Error: {norma.get('error', '')[:50]}")

            await asyncio.sleep(1)

        await browser.close()

    # Combinar con normas existentes
    todas_normas = {n['id_norma']: n for n in data['normas']}
    todas_normas.update(nuevas_normas)

    # Guardar resultado combinado
    output = {
        'fecha': datetime.now().isoformat(),
        'total': len(todas_normas),
        'normas_base': len(data['normas']),
        'normas_vinculaciones': len(nuevas_normas),
        'normas': list(todas_normas.values())
    }

    output_path = Path("data/busquedas/normas_completas.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Resumen
    print(f"\n{'=' * 70}")
    print("RESUMEN FINAL")
    print(f"{'=' * 70}")

    print(f"\nTotal normas: {len(todas_normas)}")
    print(f"  - Base inicial: {len(data['normas'])}")
    print(f"  - Nuevas (vinculaciones): {len(nuevas_normas)}")

    # Por tipo
    print("\nPor tipo de norma:")
    por_tipo = {}
    for n in todas_normas.values():
        t = n.get('tipo', 'OTRO')
        por_tipo[t] = por_tipo.get(t, 0) + 1
    for tipo, cnt in sorted(por_tipo.items(), key=lambda x: -x[1]):
        print(f"  {tipo}: {cnt}")

    # Por tema
    print("\nPor tema detectado:")
    por_tema = {}
    for n in todas_normas.values():
        for t in n.get('temas_detectados', []):
            por_tema[t] = por_tema.get(t, 0) + 1
    for tema, cnt in sorted(por_tema.items(), key=lambda x: -x[1]):
        print(f"  {tema}: {cnt}")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
