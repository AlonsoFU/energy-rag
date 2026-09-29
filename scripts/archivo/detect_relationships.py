#!/usr/bin/env python3
"""
Detectar y guardar relaciones entre normas.
Analiza títulos para encontrar MODIFICA/DEROGA/etc.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.models import (
    Norm, NormRelationship, NormType, NormStatus, RelationshipType,
    get_engine, get_session
)
from src.database.repository import NormRepository
from src.parsers.relationship_parser import RelationshipParser, RelationType


# Mapeo parser -> modelo
RELATION_TYPE_MAP = {
    RelationType.MODIFICA: RelationshipType.MODIFICA,
    RelationType.DEROGA: RelationshipType.DEROGA,
    RelationType.SUSTITUYE: RelationshipType.SUSTITUYE,
    RelationType.REGLAMENTA: RelationshipType.REGLAMENTA,
    RelationType.AGREGA: RelationshipType.AGREGA,
    RelationType.COMPLEMENTA: RelationshipType.COMPLEMENTA,
}


def detect_and_save_relationships(db_path: str = "db/bcn_norms.db"):
    """Detectar relaciones y guardarlas en la base de datos."""

    print("=" * 60)
    print("DETECCIÓN DE RELACIONES ENTRE NORMAS")
    print("=" * 60)

    # Conectar a DB
    engine = get_engine(db_path)
    session = get_session(engine)
    repo = NormRepository(session)
    parser = RelationshipParser()

    # Cargar todas las normas
    all_norms = repo.get_all_norms()
    print(f"\n📊 Total normas en DB: {len(all_norms)}")

    # Crear índice para búsqueda rápida
    norm_index = {}
    for norm in all_norms:
        if norm.numero:
            key = f"{norm.tipo.value}_{norm.numero}"
            if key not in norm_index:
                norm_index[key] = []
            norm_index[key].append(norm)

    # Estadísticas
    stats = {
        'processed': 0,
        'with_relations': 0,
        'relations_found': 0,
        'relations_matched': 0,
        'relations_not_matched': 0,
        'by_type': {rt.value: 0 for rt in RelationshipType}
    }

    # Procesar cada norma
    print("\n🔍 Analizando títulos...")

    for norm in all_norms:
        relations = parser.parse_titulo(norm.titulo)
        stats['processed'] += 1

        if relations:
            stats['with_relations'] += 1

            for rel in relations:
                stats['relations_found'] += 1

                # Buscar norma objetivo
                target_key = f"{rel.target_tipo}_{rel.target_numero}"
                candidates = norm_index.get(target_key, [])

                # Si hay año, filtrar por año
                if rel.target_año and candidates:
                    filtered = [n for n in candidates if n.año == rel.target_año]
                    if filtered:
                        candidates = filtered

                if candidates:
                    target_norm = candidates[0]  # Tomar primera coincidencia
                    stats['relations_matched'] += 1

                    # Verificar que no exista ya
                    rel_type = RELATION_TYPE_MAP.get(rel.relation_type, RelationshipType.REFERENCIA)

                    if not repo.get_relationship_exists(norm.id, target_norm.id, rel_type):
                        # Crear relación
                        new_rel = NormRelationship(
                            source_norm_id=norm.id,
                            target_norm_id=target_norm.id,
                            relationship_type=rel_type,
                            descripcion=rel.descripcion or rel.match_text,
                            detectado_en="titulo"
                        )
                        session.add(new_rel)
                        stats['by_type'][rel_type.value] += 1

                        # Actualizar estado de norma objetivo si es DEROGA
                        if rel.relation_type == RelationType.DEROGA:
                            target_norm.estado = NormStatus.DEROGADA
                        elif rel.relation_type == RelationType.MODIFICA:
                            if target_norm.estado == NormStatus.DESCONOCIDO:
                                target_norm.estado = NormStatus.MODIFICADA
                else:
                    stats['relations_not_matched'] += 1

        if stats['processed'] % 100 == 0:
            print(f"  → Procesadas: {stats['processed']}")
            session.commit()

    # Commit final
    session.commit()

    # Resultados
    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)
    print(f"\n📊 Normas procesadas: {stats['processed']}")
    print(f"📊 Normas con relaciones: {stats['with_relations']}")
    print(f"📊 Relaciones detectadas: {stats['relations_found']}")
    print(f"   ✅ Matcheadas: {stats['relations_matched']}")
    print(f"   ❌ Sin match: {stats['relations_not_matched']}")

    print(f"\n📊 Por tipo de relación:")
    for tipo, count in stats['by_type'].items():
        if count > 0:
            print(f"   {tipo}: {count}")

    # Mostrar ejemplos de relaciones
    print("\n📋 Ejemplos de relaciones encontradas:")
    sample_rels = session.query(NormRelationship).limit(10).all()
    for rel in sample_rels:
        source = session.query(Norm).get(rel.source_norm_id)
        target = session.query(Norm).get(rel.target_norm_id)
        print(f"   {source.nombre_corto} --{rel.relationship_type.value}--> {target.nombre_corto}")

    # Actualizar estadísticas finales
    final_stats = repo.get_stats()
    print(f"\n📊 Estado final de la DB:")
    print(f"   Relaciones totales: {final_stats['total_relationships']}")
    print(f"   Normas vigentes: {final_stats['by_status'].get('VIGENTE', 0)}")
    print(f"   Normas modificadas: {final_stats['by_status'].get('MODIFICADA', 0)}")
    print(f"   Normas derogadas: {final_stats['by_status'].get('DEROGADA', 0)}")

    session.close()
    return stats


if __name__ == "__main__":
    detect_and_save_relationships()
