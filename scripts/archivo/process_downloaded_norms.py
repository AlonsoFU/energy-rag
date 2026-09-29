#!/usr/bin/env python3
"""
Procesar normas descargadas y generar JSONs estructurados con relaciones.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.bcn_metadata_parser import BCNMetadataParser, ParsedNorm


def process_all_norms():
    """Procesar todas las normas descargadas."""

    print("=" * 70)
    print("PROCESANDO NORMAS DESCARGADAS")
    print("=" * 70)

    base_path = Path(__file__).parent.parent
    textos_path = base_path / "data" / "textos"
    output_path = base_path / "data" / "normas_procesadas"
    output_path.mkdir(parents=True, exist_ok=True)

    # Cargar test_group para tener nombres y metadatos correctos
    test_group_path = base_path / "data" / "test_group.json"
    metadata_conocida = {}
    if test_group_path.exists():
        with open(test_group_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for n in data['normas']:
                if n.get('id_norma'):
                    # Parsear nombre para obtener tipo y número
                    nombre = n['nombre']
                    import re
                    match = re.match(r'(Ley|Decreto|DFL|DL|Resolución)\s+(\d+(?:\.\d+)?)', nombre)
                    if match:
                        metadata_conocida[n['id_norma']] = {
                            'nombre': nombre,
                            'tipo': match.group(1).upper().replace('Ó', 'O'),
                            'numero': match.group(2).replace('.', ''),
                            'año': n.get('año'),
                            'tema': n.get('tema')
                        }
    nombres = {k: v['nombre'] for k, v in metadata_conocida.items()}

    parser = BCNMetadataParser()
    normas_procesadas = []

    # Procesar cada archivo de texto
    txt_files = list(textos_path.glob("*.txt"))
    print(f"\nArchivos a procesar: {len(txt_files)}")

    for txt_file in txt_files:
        id_norma = txt_file.stem
        nombre_conocido = nombres.get(id_norma, "")

        print(f"\n  Procesando: {id_norma} ({nombre_conocido})")

        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                texto = f.read()

            # Parsear
            norm = parser.parse(texto, id_norma)

            # Usar metadatos conocidos si existen
            if id_norma in metadata_conocida:
                meta = metadata_conocida[id_norma]
                norm.tipo = meta['tipo']
                norm.numero = meta['numero']
                if meta.get('tema'):
                    norm.titulo = meta['tema']

            # Mostrar info
            print(f"    Tipo: {norm.tipo} {norm.numero}")
            print(f"    Estado: {norm.estado}")
            print(f"    Modificada por: {len(norm.modificada_por)}")
            print(f"    Referencias: {len(norm.referencias)}")

            normas_procesadas.append(norm)

        except Exception as e:
            print(f"    ERROR: {e}")

    # Crear índice de normas por tipo+número
    indice = {}
    for norm in normas_procesadas:
        key = f"{norm.tipo}_{norm.numero}"
        indice[key] = norm.id_norma

    # Actualizar referencias con id_norma donde sea posible
    for norm in normas_procesadas:
        for mod in norm.modificada_por:
            key = f"{mod.tipo}_{mod.numero}"
            if key in indice:
                mod.id_norma = indice[key]

        for ref in norm.referencias:
            key = f"{ref.tipo}_{ref.numero}"
            if key in indice:
                ref.id_norma = indice[key]

    # Guardar JSONs individuales
    print("\n" + "-" * 70)
    print("GUARDANDO JSONs")
    print("-" * 70)

    for norm in normas_procesadas:
        # Determinar subcarpeta
        tipo_lower = norm.tipo.lower()
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

        # Nombre de archivo
        filename = f"{norm.tipo.lower()}_{norm.numero}.json"

        # Crear carpeta y guardar
        (output_path / subdir).mkdir(parents=True, exist_ok=True)
        json_path = output_path / subdir / filename

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(norm.to_dict(), f, indent=2, ensure_ascii=False)

        print(f"  Guardado: {json_path}")

    # Crear archivo consolidado con todas las normas
    consolidado = {
        "generado": datetime.now().isoformat(),
        "total": len(normas_procesadas),
        "normas": [norm.to_dict() for norm in normas_procesadas],
        "indice": indice
    }

    consolidado_path = output_path / "todas_las_normas.json"
    with open(consolidado_path, 'w', encoding='utf-8') as f:
        json.dump(consolidado, f, indent=2, ensure_ascii=False)

    print(f"\n  Consolidado: {consolidado_path}")

    # Crear grafo de relaciones
    print("\n" + "-" * 70)
    print("RELACIONES ENCONTRADAS")
    print("-" * 70)

    relaciones = []
    for norm in normas_procesadas:
        for mod in norm.modificada_por:
            relaciones.append({
                "origen": f"{mod.tipo} {mod.numero}",
                "destino": f"{norm.tipo} {norm.numero}",
                "tipo": "MODIFICA",
                "fecha": mod.fecha_do,
                "articulo": mod.articulo,
                "origen_id": mod.id_norma,
                "destino_id": norm.id_norma
            })

    print(f"\n  Total relaciones: {len(relaciones)}")
    for rel in relaciones[:20]:
        print(f"    {rel['origen']} --MODIFICA--> {rel['destino']}")
        if rel['articulo']:
            print(f"      (Art. {rel['articulo']})")

    # Guardar relaciones
    relaciones_path = output_path / "relaciones.json"
    with open(relaciones_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generado": datetime.now().isoformat(),
            "total": len(relaciones),
            "relaciones": relaciones
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Relaciones guardadas: {relaciones_path}")

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"  Normas procesadas: {len(normas_procesadas)}")
    print(f"  Relaciones encontradas: {len(relaciones)}")
    print(f"\n  Archivos generados:")
    print(f"    - {len(list(output_path.glob('**/*.json')))} JSONs individuales")
    print(f"    - todas_las_normas.json (consolidado)")
    print(f"    - relaciones.json")

    return normas_procesadas, relaciones


if __name__ == "__main__":
    process_all_norms()
