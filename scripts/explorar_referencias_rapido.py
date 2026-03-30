#!/usr/bin/env python3
"""
Explorar referencias desde normas conocidas - versión rápida.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def explorar_norma(id_norma: str, page) -> list:
    """Extraer todas las referencias de una norma."""
    results = []

    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"
    await page.goto(url, wait_until='networkidle', timeout=30000)
    await asyncio.sleep(2)

    html = await page.content()

    # Buscar todos los idNorma referenciados
    pattern = r'idNorma=(\d+)'
    ids_encontrados = set(re.findall(pattern, html))
    ids_encontrados.discard(id_norma)  # Quitar la propia norma

    # Para cada ID, extraer tipo y número del contexto
    for ref_id in ids_encontrados:
        # Buscar el contexto del link
        context_pattern = rf'idNorma={ref_id}[^"]*"[^>]*>([^<]+)</a>'
        context_match = re.search(context_pattern, html)

        if context_match:
            texto = context_match.group(1).strip()
            norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RES)\s*N?[°º]?\s*(\d+)', texto, re.IGNORECASE)

            if norm_match:
                tipo = norm_match.group(1).upper()
                if tipo == 'DTO':
                    tipo = 'DECRETO'
                elif tipo == 'RES':
                    tipo = 'RESOLUCION'

                results.append({
                    'id_norma': ref_id,
                    'tipo': tipo,
                    'numero': norm_match.group(2),
                    'texto': texto[:100]
                })

    return results


async def main():
    print("=" * 70)
    print("EXPLORANDO REFERENCIAS DESDE NORMAS CONOCIDAS")
    print("=" * 70)

    # Normas semilla del sector eléctrico
    SEMILLAS = {
        "250604": "Decreto 62 (Potencia)",
        "258171": "DFL 4 (LGSE)",
        "1109624": "Ley 20936 (Transmisión)",
        "1215040": "Decreto 10 (Valorización)",
        "1191446": "Decreto 52 (Coordinador)",
    }

    todas_normas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        for id_norma, nombre in SEMILLAS.items():
            print(f"\n[{nombre}]")

            try:
                refs = await explorar_norma(id_norma, page)
                print(f"  Referencias encontradas: {len(refs)}")

                for r in refs:
                    key = r['id_norma']
                    if key not in todas_normas:
                        todas_normas[key] = {
                            **r,
                            'encontrado_desde': nombre
                        }
                        print(f"    + {r['tipo']} {r['numero']} (id: {key})")

            except Exception as e:
                print(f"  Error: {e}")

        await browser.close()

    # También agregar las semillas
    for id_norma, nombre in SEMILLAS.items():
        if id_norma not in todas_normas:
            match = re.match(r'(\w+)\s+(\d+)', nombre)
            if match:
                todas_normas[id_norma] = {
                    'id_norma': id_norma,
                    'tipo': match.group(1).upper(),
                    'numero': match.group(2),
                    'texto': nombre,
                    'encontrado_desde': 'semilla'
                }

    # Guardar
    output = {
        'descripcion': 'Normas del mercado eléctrico chileno - transacciones económicas',
        'fecha': datetime.now().isoformat(),
        'semillas': list(SEMILLAS.keys()),
        'total': len(todas_normas),
        'normas': list(todas_normas.values())
    }

    output_path = Path("data/busquedas/transacciones_economicas.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Resumen
    print(f"\n{'=' * 70}")
    print(f"TOTAL: {len(todas_normas)} normas encontradas")
    print(f"{'=' * 70}")

    por_tipo = {}
    for n in todas_normas.values():
        t = n.get('tipo', 'OTRO')
        por_tipo[t] = por_tipo.get(t, 0) + 1

    for tipo, cnt in sorted(por_tipo.items(), key=lambda x: -x[1]):
        print(f"  {tipo}: {cnt}")

    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
