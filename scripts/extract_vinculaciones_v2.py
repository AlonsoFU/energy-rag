#!/usr/bin/env python3
"""
Extrae vinculaciones completas de BCN - Versión simplificada.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def extract_vinculaciones(id_norma: str):
    """Extraer vinculaciones de una norma."""

    print(f"\n{'=' * 60}")
    print(f"EXTRAYENDO VINCULACIONES DE NORMA {id_norma}")
    print(f"{'=' * 60}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)

        page = await context.new_page()

        url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
        print(f"\nAccediendo a: {url}")

        await page.goto(url, wait_until='networkidle', timeout=60000)
        await asyncio.sleep(3)

        # 1. Extraer modificaciones inline
        print("\n1. Extrayendo modificaciones inline...")

        # Obtener el HTML completo
        html = await page.content()

        # Buscar patrones de modificación inline
        # <a href="navegar?idNorma=1204012...">Decreto 70, ENERGÍA<br>Art. primero N° 1<br>D.O. 05.06.2024</a>
        # También incluye DTO como abreviación
        inline_pattern = r'<a[^>]*href="[^"]*idNorma=(\d+)[^"]*"[^>]*>\s*(DTO|Decreto|Ley|DFL|DL|RES|Resoluci[oó]n)\s+(\d+)'
        inline_matches = re.findall(inline_pattern, html, re.IGNORECASE)

        mods_inline = {}
        for match in inline_matches:
            id_mod = match[0]
            tipo = match[1].upper()
            if tipo == 'DTO':
                tipo = 'DECRETO'
            elif tipo == 'RES':
                tipo = 'RESOLUCION'
            tipo = tipo.replace('Ó', 'O')
            numero = match[2]
            key = id_mod
            if key not in mods_inline and id_mod != id_norma:
                mods_inline[key] = {
                    'id_norma': id_mod,
                    'tipo': tipo,
                    'numero': numero,
                    'fuente': 'inline'
                }

        print(f"   Encontradas: {len(mods_inline)}")

        # 2. Buscar en tabla de versiones
        print("\n2. Extrayendo de tabla versiones...")

        # Buscar links con idVersion que son las normas modificadoras
        # Patron: href="...idNorma=258729&idVersion=2007-03-02">DTO 44 MINISTERIO...
        version_pattern = r'href="[^"]*idNorma=(\d+)[^"]*idVersion[^"]*"[^>]*>\s*([^<]+)</a>'
        version_matches = re.findall(version_pattern, html)

        mods_versiones = {}
        for match in version_matches:
            id_mod = match[0]
            texto = match[1].strip()

            # Extraer tipo y número del texto
            # BCN usa "DTO" como abreviación de Decreto
            norm_match = re.search(r'(DTO|Decreto|LEY|Ley|DFL|DL|RES|Resoluci[oó]n)\s+(\d+)', texto, re.IGNORECASE)
            if norm_match and id_mod != id_norma:  # Excluir la propia norma
                key = id_mod
                if key not in mods_versiones and key not in mods_inline:
                    tipo = norm_match.group(1).upper()
                    if tipo == 'DTO':
                        tipo = 'DECRETO'
                    elif tipo == 'RES':
                        tipo = 'RESOLUCION'
                    tipo = tipo.replace('Ó', 'O')

                    mods_versiones[key] = {
                        'id_norma': id_mod,
                        'tipo': tipo,
                        'numero': norm_match.group(2),
                        'fuente': 'versiones'
                    }

        print(f"   Encontradas: {len(mods_versiones)}")

        # 3. Ir a página de vinculaciones MODIFICACION
        print("\n3. Accediendo a página de MODIFICACION...")

        vinc_url = f"https://www.bcn.cl/leychile/Consulta/nav_vinc_modificacion?idNorma={id_norma}"
        try:
            await page.goto(vinc_url, wait_until='networkidle', timeout=60000)
            await asyncio.sleep(2)

            vinc_html = await page.content()

            # Buscar todas las normas listadas (incluye DTO como abreviación)
            vinc_pattern = r'idNorma=(\d+)[^"]*"[^>]*>\s*(?:<[^>]*>)*\s*(DTO|Decreto|LEY|Ley|DFL|DL|RES|Resoluci[oó]n)\s+(\d+)'
            vinc_matches = re.findall(vinc_pattern, vinc_html, re.IGNORECASE)

            mods_vinc = {}
            for match in vinc_matches:
                id_mod = match[0]
                tipo = match[1].upper()
                if tipo == 'DTO':
                    tipo = 'DECRETO'
                elif tipo == 'RES':
                    tipo = 'RESOLUCION'
                tipo = tipo.replace('Ó', 'O')
                numero = match[2]
                key = id_mod
                if key not in mods_vinc and key not in mods_inline and key not in mods_versiones:
                    if id_mod != id_norma:  # Excluir la propia norma
                        mods_vinc[key] = {
                            'id_norma': id_mod,
                            'tipo': tipo,
                            'numero': numero,
                            'fuente': 'vinculaciones_page'
                        }

            print(f"   Encontradas: {len(mods_vinc)}")

        except Exception as e:
            print(f"   Error: {e}")
            mods_vinc = {}

        await browser.close()

        # Consolidar todas las modificaciones
        all_mods = {**mods_inline, **mods_versiones, **mods_vinc}

        print(f"\n{'=' * 60}")
        print(f"RESUMEN: {len(all_mods)} modificaciones únicas")
        print(f"{'=' * 60}")

        for mod in all_mods.values():
            print(f"  - {mod['tipo']} {mod['numero']} (id: {mod['id_norma']}) [{mod['fuente']}]")

        # Guardar resultado
        result = {
            'id_norma': id_norma,
            'extracted_at': datetime.now().isoformat(),
            'modificada_por': list(all_mods.values())
        }

        output_path = Path("data/vinculaciones") / f"{id_norma}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\nGuardado en: {output_path}")

        return result


if __name__ == "__main__":
    asyncio.run(extract_vinculaciones("250604"))
