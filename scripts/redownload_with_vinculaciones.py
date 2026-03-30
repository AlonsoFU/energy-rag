#!/usr/bin/env python3
"""
Re-descargar normas con el crawler mejorado que extrae idNorma de vinculaciones.
Guarda las vinculaciones estructuradas directamente del HTML (no del texto).
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.crawlers.norm_detail_crawler import NormDetailCrawler, NormData


async def redownload_all():
    """Re-descargar todas las normas del test group con vinculaciones estructuradas."""

    print("=" * 70)
    print("RE-DESCARGANDO NORMAS CON VINCULACIONES ESTRUCTURADAS")
    print("=" * 70)

    base_path = Path(__file__).parent.parent
    test_group_path = base_path / "data" / "test_group.json"
    output_path = base_path / "data" / "normas_completas"
    output_path.mkdir(parents=True, exist_ok=True)

    # Cargar test_group
    with open(test_group_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    normas_config = data['normas']
    print(f"\nNormas a descargar: {len(normas_config)}")

    resultados = []

    async with NormDetailCrawler(headless=True) as crawler:
        for i, config in enumerate(normas_config, 1):
            id_norma = config.get('id_norma')
            nombre = config.get('nombre', '?')

            if not id_norma:
                print(f"\n[{i}/{len(normas_config)}] {nombre}: Sin idNorma, saltando")
                continue

            print(f"\n[{i}/{len(normas_config)}] {nombre} (idNorma={id_norma})")

            try:
                # Descargar con crawler mejorado
                norm = await crawler.fetch_norm(id_norma)

                if norm:
                    # Sobrescribir tipo/numero con la config si es necesario
                    if config.get('nombre'):
                        import re
                        match = re.match(r'(Ley|Decreto|DFL|DL|Resolución)\s+(\d+(?:\.\d+)?)', nombre)
                        if match:
                            norm_tipo = match.group(1).upper().replace('Ó', 'O')
                            norm_numero = match.group(2).replace('.', '')
                            # Solo sobrescribir si el crawler no lo detectó bien
                            if not norm.tipo or norm.tipo == 'DESCONOCIDO':
                                norm = NormData(
                                    id_norma=norm.id_norma,
                                    tipo=norm_tipo,
                                    numero=norm_numero,
                                    titulo=norm.titulo or config.get('tema', ''),
                                    fecha_publicacion=norm.fecha_publicacion,
                                    fecha_promulgacion=norm.fecha_promulgacion,
                                    organismo=norm.organismo,
                                    estado=norm.estado,
                                    url=norm.url,
                                    texto_completo=norm.texto_completo,
                                    content_hash=norm.content_hash,
                                    vinculaciones=norm.vinculaciones,
                                    versiones=norm.versiones,
                                    extracted_at=norm.extracted_at
                                )

                    # Deduplicar vinculaciones.modificada_por
                    seen = set()
                    unique_mods = []
                    for mod in norm.vinculaciones.get('modificada_por', []):
                        key = f"{mod.get('id_norma')}-{mod.get('articulo', '')}"
                        if key not in seen:
                            seen.add(key)
                            unique_mods.append(mod)
                    norm.vinculaciones['modificada_por'] = unique_mods

                    # Guardar JSON completo
                    tipo_lower = norm.tipo.lower() if norm.tipo else 'otros'
                    if tipo_lower == 'ley':
                        subdir = 'leyes'
                    elif tipo_lower == 'dfl':
                        subdir = 'dfl'
                    elif tipo_lower == 'decreto':
                        subdir = 'decretos'
                    elif tipo_lower == 'resolucion':
                        subdir = 'resoluciones'
                    else:
                        subdir = 'otros'

                    (output_path / subdir).mkdir(parents=True, exist_ok=True)
                    filename = f"{tipo_lower}_{norm.numero}.json"
                    json_path = output_path / subdir / filename

                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(asdict(norm), f, indent=2, ensure_ascii=False)

                    print(f"   Tipo: {norm.tipo} {norm.numero}")
                    print(f"   Vinculaciones:")
                    print(f"     - modificada_por: {len(norm.vinculaciones.get('modificada_por', []))} (con idNorma)")
                    print(f"     - referencias: {len(norm.vinculaciones.get('referencias', []))}")
                    print(f"   Guardado: {json_path}")

                    resultados.append({
                        'nombre': nombre,
                        'id_norma': id_norma,
                        'tipo': norm.tipo,
                        'numero': norm.numero,
                        'modificada_por': len(norm.vinculaciones.get('modificada_por', [])),
                        'texto_len': len(norm.texto_completo),
                        'path': str(json_path)
                    })
                else:
                    print(f"   ERROR: No se pudo descargar")

            except Exception as e:
                print(f"   ERROR: {e}")

            # Pausa entre descargas
            await asyncio.sleep(2)

    # Construir grafo de relaciones con idNorma
    print("\n" + "=" * 70)
    print("CONSTRUYENDO GRAFO DE RELACIONES")
    print("=" * 70)

    relaciones = []

    # Leer todos los JSONs generados
    all_norms = {}
    for json_file in output_path.glob("**/*.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            norm_data = json.load(f)
            all_norms[norm_data['id_norma']] = norm_data

    print(f"\nNormas cargadas: {len(all_norms)}")

    for norm_data in all_norms.values():
        id_destino = norm_data['id_norma']
        tipo_destino = norm_data['tipo']
        numero_destino = norm_data['numero']

        for mod in norm_data.get('vinculaciones', {}).get('modificada_por', []):
            id_origen = mod.get('id_norma')
            if id_origen:
                relaciones.append({
                    "origen": f"{mod.get('tipo', '?')} {mod.get('numero', '?')}",
                    "destino": f"{tipo_destino} {numero_destino}",
                    "tipo": "MODIFICA",
                    "fecha": mod.get('fecha_do'),
                    "articulo": mod.get('articulo'),
                    "origen_id": id_origen,
                    "destino_id": id_destino,
                    "organismo_origen": mod.get('organismo')
                })

    print(f"\nRelaciones con idNorma: {len(relaciones)}")
    for rel in relaciones:
        print(f"  {rel['origen']} ({rel['origen_id']}) --MODIFICA--> {rel['destino']} ({rel['destino_id']})")
        if rel['articulo']:
            print(f"    Art. {rel['articulo']} - {rel['fecha']}")

    # Guardar relaciones
    relaciones_path = output_path / "relaciones_con_id.json"
    with open(relaciones_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generado": datetime.now().isoformat(),
            "total": len(relaciones),
            "nota": "Relaciones extraidas directamente del HTML de BCN con idNorma de la norma modificadora",
            "relaciones": relaciones
        }, f, indent=2, ensure_ascii=False)

    print(f"\nRelaciones guardadas: {relaciones_path}")

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"  Normas descargadas: {len(resultados)}")
    print(f"  Relaciones con idNorma: {len(relaciones)}")
    print(f"\n  Output: {output_path}")

    return resultados, relaciones


if __name__ == "__main__":
    asyncio.run(redownload_all())
