#!/usr/bin/env python3
"""
Generar JSONs estructurados con relaciones bidireccionales.
- Estructura jerárquica: Títulos > Artículos
- Modificaciones por artículo
- Referencias con contexto
- Vinculaciones bidireccionales entre normas
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parsers.norm_structure_parser import NormStructureParser, NormaEstructurada


def load_metadata() -> Dict[str, dict]:
    """Cargar metadatos conocidos de test_group.json."""
    base_path = Path(__file__).parent.parent
    test_group_path = base_path / "data" / "test_group.json"

    metadata = {}
    if test_group_path.exists():
        with open(test_group_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        import re
        for n in data['normas']:
            if n.get('id_norma'):
                nombre = n['nombre']
                match = re.match(r'(Ley|Decreto|DFL|DL|Resolución)\s+(\d+(?:\.\d+)?)', nombre)
                if match:
                    metadata[n['id_norma']] = {
                        'nombre': nombre,
                        'tipo': match.group(1).upper().replace('Ó', 'O'),
                        'numero': match.group(2).replace('.', ''),
                        'año': n.get('año'),
                        'tema': n.get('tema')
                    }

    return metadata


def build_norm_index(normas: List[NormaEstructurada]) -> Dict[str, str]:
    """Construir índice tipo_numero -> id_norma."""
    indice = {}
    for norma in normas:
        key = f"{norma.tipo}_{norma.numero}"
        indice[key] = norma.id_norma
    return indice


def resolve_references(normas: List[NormaEstructurada], indice: Dict[str, str]):
    """Resolver id_norma de referencias y modificaciones."""
    for norma in normas:
        # Resolver modificaciones
        for mod in norma.modificada_por:
            key = f"{mod.tipo}_{mod.numero}"
            if key in indice:
                mod.id_norma = indice[key]

        # Resolver referencias
        for ref in norma.todas_referencias:
            key = f"{ref.tipo}_{ref.numero}"
            if key in indice:
                ref.id_norma = indice[key]


def build_bidirectional_relations(normas: List[NormaEstructurada]) -> List[dict]:
    """
    Construir relaciones bidireccionales.

    Si D.70 modifica D.62:
    - D.62 tiene "modificada_por": [D.70]
    - D.70 tiene "modifica_a": [D.62]
    """
    relaciones = []
    normas_dict = {n.id_norma: n for n in normas}

    for norma in normas:
        for mod in norma.modificada_por:
            # Crear relación
            relacion = {
                "origen_id": mod.id_norma,
                "origen": f"{mod.tipo} {mod.numero}",
                "destino_id": norma.id_norma,
                "destino": f"{norma.tipo} {norma.numero}",
                "tipo_relacion": "MODIFICA",
                "fecha_do": mod.fecha_do,
                "articulo_modificador": mod.articulo_modificador,
                "organismo": mod.organismo
            }
            relaciones.append(relacion)

    return relaciones


def generate_structured_jsons():
    """Procesar todas las normas y generar JSONs estructurados."""

    print("=" * 70)
    print("GENERANDO JSONs ESTRUCTURADOS CON RELACIONES")
    print("=" * 70)

    base_path = Path(__file__).parent.parent
    textos_path = base_path / "data" / "textos"
    output_path = base_path / "data" / "normas_estructuradas"
    output_path.mkdir(parents=True, exist_ok=True)

    # Cargar metadatos conocidos
    metadata_conocida = load_metadata()
    print(f"\nMetadatos conocidos: {len(metadata_conocida)} normas")

    # Parsear todas las normas
    parser = NormStructureParser()
    normas: List[NormaEstructurada] = []

    txt_files = list(textos_path.glob("*.txt"))
    print(f"Archivos a procesar: {len(txt_files)}")

    for txt_file in txt_files:
        id_norma = txt_file.stem

        print(f"\n  Procesando: {id_norma}", end="")

        try:
            with open(txt_file, 'r', encoding='utf-8') as f:
                texto = f.read()

            # Usar metadatos conocidos si existen
            meta = metadata_conocida.get(id_norma, {})

            norma = parser.parse(texto, id_norma, meta)
            normas.append(norma)

            print(f" -> {norma.tipo} {norma.numero}")
            print(f"      Artículos: {len(norma.articulos)}, "
                  f"Modificaciones: {len(norma.modificada_por)}, "
                  f"Referencias: {len(norma.todas_referencias)}")

        except Exception as e:
            print(f" ERROR: {e}")

    # Construir índice
    print("\n" + "-" * 70)
    print("RESOLVIENDO REFERENCIAS CRUZADAS")
    print("-" * 70)

    indice = build_norm_index(normas)
    print(f"Índice construido: {len(indice)} normas")

    # Resolver referencias
    resolve_references(normas, indice)

    # Contar referencias resueltas
    refs_resueltas = sum(
        1 for n in normas
        for r in n.todas_referencias
        if r.id_norma
    )
    mods_resueltas = sum(
        1 for n in normas
        for m in n.modificada_por
        if m.id_norma
    )
    print(f"Referencias resueltas: {refs_resueltas}")
    print(f"Modificaciones resueltas: {mods_resueltas}")

    # Construir relaciones bidireccionales
    relaciones = build_bidirectional_relations(normas)
    print(f"Relaciones bidireccionales: {len(relaciones)}")

    # Guardar JSONs individuales
    print("\n" + "-" * 70)
    print("GUARDANDO JSONs ESTRUCTURADOS")
    print("-" * 70)

    for norma in normas:
        # Determinar subcarpeta
        tipo_lower = norma.tipo.lower()
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
        filename = f"{norma.tipo.lower()}_{norma.numero}.json"

        # Crear carpeta y guardar
        (output_path / subdir).mkdir(parents=True, exist_ok=True)
        json_path = output_path / subdir / filename

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(norma.to_dict(), f, indent=2, ensure_ascii=False)

        print(f"  {json_path}")

    # Guardar índice global
    indice_path = output_path / "indice_normas.json"
    with open(indice_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generado": datetime.now().isoformat(),
            "total": len(normas),
            "indice": indice,
            "normas": [
                {
                    "id_norma": n.id_norma,
                    "tipo": n.tipo,
                    "numero": n.numero,
                    "nombre": n.nombre,
                    "estado": n.estado,
                    "articulos": len(n.articulos),
                    "modificada_por": len(n.modificada_por),
                    "referencias": len(n.todas_referencias)
                }
                for n in normas
            ]
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Índice: {indice_path}")

    # Guardar relaciones
    relaciones_path = output_path / "relaciones_bidireccionales.json"
    with open(relaciones_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generado": datetime.now().isoformat(),
            "total": len(relaciones),
            "relaciones": relaciones
        }, f, indent=2, ensure_ascii=False)
    print(f"  Relaciones: {relaciones_path}")

    # Resumen
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"  Normas procesadas: {len(normas)}")
    print(f"  Relaciones encontradas: {len(relaciones)}")

    # Mostrar grafo de relaciones
    print("\n  Grafo de modificaciones:")
    for rel in relaciones:
        origen = rel['origen'] if rel['origen_id'] else f"({rel['origen']})"
        print(f"    {origen} --MODIFICA--> {rel['destino']}")
        if rel['fecha_do']:
            print(f"      D.O. {rel['fecha_do']}")

    return normas, relaciones


if __name__ == "__main__":
    generate_structured_jsons()
