#!/usr/bin/env python3
"""
Exploración ampliada: distribución, medidas, y análisis de referencias.
"""

import asyncio
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def explorar_norma(id_norma: str, page) -> dict:
    """Extraer referencias y texto de una norma."""
    url = f"https://www.bcn.cl/leychile/navegar?idNorma={id_norma}"

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(1.5)

        html = await page.content()

        # Extraer título
        titulo_match = re.search(r'<title>([^<]+)</title>', html)
        titulo = titulo_match.group(1) if titulo_match else ""

        # Extraer todas las referencias (idNorma)
        refs = set(re.findall(r'idNorma=(\d+)', html))
        refs.discard(id_norma)

        # Clasificar referencias por tipo
        referencias = []
        for ref_id in refs:
            context = re.search(rf'idNorma={ref_id}[^"]*"[^>]*>([^<]+)</a>', html)
            if context:
                texto = context.group(1).strip()
                norm_match = re.search(r'(LEY|DECRETO|DFL|DL|RESOLUCION|DTO|RES)\s*N?[°º]?\s*(\d+)', texto, re.IGNORECASE)
                if norm_match:
                    tipo = norm_match.group(1).upper()
                    if tipo == 'DTO':
                        tipo = 'DECRETO'
                    referencias.append({
                        'id': ref_id,
                        'tipo': tipo,
                        'numero': norm_match.group(2),
                        'texto': texto[:80]
                    })

        # Buscar palabras clave en el contenido
        texto_lower = html.lower()
        temas = []
        if 'distribuci' in texto_lower:
            temas.append('DISTRIBUCION')
        if 'transmisi' in texto_lower:
            temas.append('TRANSMISION')
        if 'generaci' in texto_lower:
            temas.append('GENERACION')
        if 'medid' in texto_lower or 'medici' in texto_lower:
            temas.append('MEDIDAS')
        if 'tarifa' in texto_lower:
            temas.append('TARIFAS')
        if 'potencia' in texto_lower:
            temas.append('POTENCIA')
        if 'energ' in texto_lower:
            temas.append('ENERGIA')
        if 'peaje' in texto_lower:
            temas.append('PEAJES')

        return {
            'id_norma': id_norma,
            'titulo': titulo[:150],
            'referencias': referencias,
            'temas': temas,
            'num_refs': len(referencias)
        }

    except Exception as e:
        return {'id_norma': id_norma, 'error': str(e)}


async def main():
    print("=" * 70)
    print("EXPLORACIÓN AMPLIADA: DISTRIBUCIÓN, MEDIDAS, REFERENCIAS")
    print("=" * 70)

    # Cargar normas ya encontradas
    busqueda_path = Path("data/busquedas/transacciones_economicas.json")
    with open(busqueda_path) as f:
        data = json.load(f)

    normas_existentes = {n['id_norma']: n for n in data['normas']}
    print(f"\nNormas existentes: {len(normas_existentes)}")

    # Analizar referencias de cada norma
    todas_referencias = defaultdict(list)
    normas_analizadas = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        stealth = Stealth()
        await stealth.apply_stealth_async(context)
        page = await context.new_page()

        # Analizar las normas más importantes (primeras 15)
        normas_a_analizar = list(normas_existentes.keys())[:15]

        for i, id_norma in enumerate(normas_a_analizar, 1):
            info = normas_existentes[id_norma]
            print(f"\n[{i}/{len(normas_a_analizar)}] Analizando {info.get('tipo', '?')} {info.get('numero', '?')} (id: {id_norma})")

            resultado = await explorar_norma(id_norma, page)
            normas_analizadas[id_norma] = resultado

            if 'error' not in resultado:
                print(f"   Referencias: {resultado['num_refs']}")
                print(f"   Temas: {', '.join(resultado['temas']) if resultado['temas'] else 'N/A'}")

                # Registrar referencias
                for ref in resultado['referencias']:
                    todas_referencias[ref['id']].append({
                        'desde': id_norma,
                        'tipo': ref['tipo'],
                        'numero': ref['numero']
                    })

                    # Agregar nuevas normas encontradas
                    if ref['id'] not in normas_existentes:
                        normas_existentes[ref['id']] = {
                            'id_norma': ref['id'],
                            'tipo': ref['tipo'],
                            'numero': ref['numero'],
                            'encontrado_desde': f"{info.get('tipo', '')} {info.get('numero', '')}"
                        }
                        print(f"      + Nueva: {ref['tipo']} {ref['numero']} (id: {ref['id']})")

        await browser.close()

    # Análisis de temas
    print(f"\n{'=' * 70}")
    print("ANÁLISIS DE TEMAS")
    print("=" * 70)

    temas_count = defaultdict(int)
    normas_por_tema = defaultdict(list)

    for id_norma, info in normas_analizadas.items():
        for tema in info.get('temas', []):
            temas_count[tema] += 1
            normas_por_tema[tema].append(id_norma)

    for tema, count in sorted(temas_count.items(), key=lambda x: -x[1]):
        print(f"\n  {tema}: {count} normas")
        for id_n in normas_por_tema[tema][:3]:
            n = normas_existentes.get(id_n, {})
            print(f"    - {n.get('tipo', '?')} {n.get('numero', '?')}")

    # Normas más referenciadas
    print(f"\n{'=' * 70}")
    print("NORMAS MÁS REFERENCIADAS")
    print("=" * 70)

    refs_ordenadas = sorted(todas_referencias.items(), key=lambda x: -len(x[1]))[:10]
    for id_ref, lista in refs_ordenadas:
        n = normas_existentes.get(id_ref, {})
        print(f"\n  {n.get('tipo', '?')} {n.get('numero', '?')} (id: {id_ref})")
        print(f"    Referenciada por {len(lista)} normas:")
        for r in lista[:5]:
            print(f"      - desde id {r['desde']}")

    # Guardar análisis completo
    output = {
        'fecha': datetime.now().isoformat(),
        'total_normas': len(normas_existentes),
        'normas_analizadas': len(normas_analizadas),
        'temas': dict(temas_count),
        'normas_por_tema': {k: v for k, v in normas_por_tema.items()},
        'referencias_cruzadas': {k: v for k, v in list(todas_referencias.items())[:50]},
        'normas': list(normas_existentes.values())
    }

    output_path = Path("data/busquedas/analisis_ampliado.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"RESUMEN FINAL")
    print(f"{'=' * 70}")
    print(f"  Total normas: {len(normas_existentes)}")
    print(f"  Normas analizadas: {len(normas_analizadas)}")
    print(f"  Temas detectados: {len(temas_count)}")
    print(f"\nGuardado en: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
