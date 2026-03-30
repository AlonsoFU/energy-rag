#!/usr/bin/env python3
"""
Migración de normas BCN desde JSON a SQLite.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.models import (
    Norm, NormType, NormStatus,
    init_db, get_session
)
from src.database.repository import NormRepository


# Mapeo de meses español a número
MESES = {
    'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AGO': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12
}


def parse_fecha(fecha_str: str) -> datetime:
    """Parsear fecha formato BCN: '08-ABR-2024'."""
    try:
        parts = fecha_str.split('-')
        if len(parts) == 3:
            dia = int(parts[0])
            mes = MESES.get(parts[1].upper(), 1)
            año = int(parts[2])
            return datetime(año, mes, dia)
    except:
        pass
    return None


def parse_tipo_numero(tipo_str: str) -> tuple:
    """
    Parsear tipo y número de string como 'DECRETO 62' o 'LEY 20936'.

    Returns: (NormType, numero_str)
    """
    tipo_str = tipo_str.strip().upper()

    # Patrones para extraer tipo y número
    patterns = [
        (r'^(LEY)\s*(\d+)', NormType.LEY),
        (r'^(DFL)\s*(\d+)', NormType.DFL),
        (r'^(DL)\s*(\d+)', NormType.DL),
        (r'^(DECRETO)\s*(\d+)', NormType.DECRETO),
        (r'^(RESOLUCIÓN|RESOLUCION)\s*(\d+)', NormType.RESOLUCION),
        (r'^(AUTO)\s+', NormType.AUTO),
        (r'^(AUTORIZA)', NormType.OTRO),
    ]

    for pattern, norm_type in patterns:
        match = re.match(pattern, tipo_str)
        if match:
            numero = match.group(2) if len(match.groups()) > 1 else None
            return norm_type, numero

    return NormType.OTRO, None


def normalizar_organismo(organismo: str) -> str:
    """Normalizar nombre de organismo."""
    if not organismo:
        return None

    organismo_upper = organismo.upper()

    if 'ENERGÍA' in organismo_upper or 'ENERGIA' in organismo_upper:
        if 'COMISIÓN NACIONAL' in organismo_upper or 'CNE' in organismo_upper:
            return 'CNE'
        return 'MIN_ENERGIA'

    if 'ELECTRICIDAD' in organismo_upper or 'SEC' in organismo_upper:
        return 'SEC'

    if 'ECONOMÍA' in organismo_upper or 'ECONOMIA' in organismo_upper:
        return 'MIN_ECONOMIA'

    if 'HACIENDA' in organismo_upper:
        return 'MIN_HACIENDA'

    if 'MEDIO AMBIENTE' in organismo_upper:
        return 'MIN_MEDIO_AMBIENTE'

    if 'MINERÍA' in organismo_upper or 'MINERIA' in organismo_upper:
        return 'MIN_MINERIA'

    if 'OBRAS PÚBLICAS' in organismo_upper:
        return 'MOP'

    if 'INTERIOR' in organismo_upper:
        return 'MIN_INTERIOR'

    return 'OTRO'


def detectar_estado(titulo: str) -> NormStatus:
    """Detectar estado de norma basado en título."""
    titulo_upper = titulo.upper()

    if 'DERÓGASE' in titulo_upper or 'DEROGASE' in titulo_upper:
        return NormStatus.VIGENTE  # La norma que deroga está vigente

    if 'MODIFICA' in titulo_upper:
        return NormStatus.VIGENTE  # La norma que modifica está vigente

    return NormStatus.DESCONOCIDO


def migrate_json_to_sqlite(json_path: str, db_path: str = "db/bcn_norms.db"):
    """Migrar datos desde JSON a SQLite."""

    print("=" * 60)
    print("MIGRACIÓN BCN: JSON → SQLite")
    print("=" * 60)

    # Cargar JSON
    print(f"\n📂 Cargando JSON: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Inicializar DB
    print(f"🗄️  Inicializando DB: {db_path}")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = init_db(db_path)
    session = get_session(engine)
    repo = NormRepository(session)

    # Coleccionar todas las normas únicas
    normas_unicas = {}

    for materia, normas in data.get('materias', {}).items():
        for norma_data in normas:
            # Crear key única
            key = f"{norma_data['tipo']}_{norma_data['fecha']}"

            if key not in normas_unicas:
                norma_data['_materias'] = norma_data.get('materias', [materia])
                normas_unicas[key] = norma_data
            else:
                # Agregar materias adicionales
                existing_materias = normas_unicas[key].get('_materias', [])
                for m in norma_data.get('materias', [materia]):
                    if m not in existing_materias:
                        existing_materias.append(m)
                normas_unicas[key]['_materias'] = existing_materias

    print(f"\n📊 Total normas únicas: {len(normas_unicas)}")

    # Migrar cada norma
    migradas = 0
    errores = 0

    for key, norma_data in normas_unicas.items():
        try:
            tipo, numero = parse_tipo_numero(norma_data['tipo'])
            fecha_pub = parse_fecha(norma_data['fecha'])

            norm = Norm(
                tipo=tipo,
                numero=numero,
                tipo_texto=norma_data['tipo'],
                titulo=norma_data['titulo'],
                fecha=norma_data['fecha'],
                fecha_publicacion=fecha_pub,
                año=norma_data.get('año'),
                organismo=norma_data.get('organismo'),
                organismo_normalizado=normalizar_organismo(norma_data.get('organismo')),
                estado=detectar_estado(norma_data['titulo']),
                materias=json.dumps(norma_data.get('_materias', []), ensure_ascii=False),
                busqueda_original=norma_data.get('busqueda_original')
            )

            session.add(norm)
            migradas += 1

            if migradas % 100 == 0:
                print(f"  → Migradas: {migradas}")
                session.commit()

        except Exception as e:
            errores += 1
            print(f"  ❌ Error en {key}: {e}")

    # Commit final
    session.commit()

    # Estadísticas
    stats = repo.get_stats()

    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"✅ Normas migradas: {migradas}")
    print(f"❌ Errores: {errores}")
    print(f"\n📊 Por tipo:")
    for tipo, count in stats['by_type'].items():
        if count > 0:
            print(f"   {tipo}: {count}")
    print(f"\n📊 Por estado:")
    for status, count in stats['by_status'].items():
        if count > 0:
            print(f"   {status}: {count}")

    session.close()
    print(f"\n✅ Base de datos creada: {db_path}")
    return migradas


if __name__ == "__main__":
    json_path = Path(__file__).parent.parent / "data" / "raw" / "bcn_investigacion_ampliada.json"
    migrate_json_to_sqlite(str(json_path))
