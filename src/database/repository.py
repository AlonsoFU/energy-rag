"""
Repositorio para acceso a datos de normas BCN.
"""

from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func
from .models import Norm, NormRelationship, NormType, NormStatus, RelationshipType


class NormRepository:
    """Repositorio para operaciones CRUD de normas."""

    def __init__(self, session: Session):
        self.session = session

    # --- CRUD Normas ---

    def add_norm(self, norm: Norm) -> Norm:
        """Agregar una norma."""
        self.session.add(norm)
        self.session.commit()
        return norm

    def add_norms_bulk(self, norms: List[Norm]) -> int:
        """Agregar múltiples normas."""
        self.session.add_all(norms)
        self.session.commit()
        return len(norms)

    def get_norm_by_id(self, norm_id: int) -> Optional[Norm]:
        """Obtener norma por ID interno."""
        return self.session.query(Norm).filter(Norm.id == norm_id).first()

    def get_norm_by_tipo_numero(self, tipo: NormType, numero: str) -> Optional[Norm]:
        """Obtener norma por tipo y número."""
        return self.session.query(Norm).filter(
            Norm.tipo == tipo,
            Norm.numero == numero
        ).first()

    def get_norm_by_tipo_numero_año(self, tipo: NormType, numero: str, año: int) -> Optional[Norm]:
        """Obtener norma por tipo, número y año."""
        return self.session.query(Norm).filter(
            Norm.tipo == tipo,
            Norm.numero == numero,
            Norm.año == año
        ).first()

    def find_norm_by_reference(self, tipo_texto: str, numero: str, año: int = None) -> Optional[Norm]:
        """Buscar norma por referencia textual (ej: 'DECRETO 62')."""
        query = self.session.query(Norm).filter(
            Norm.numero == numero
        )

        # Mapear texto a tipo
        tipo_map = {
            'LEY': NormType.LEY,
            'DECRETO': NormType.DECRETO,
            'DFL': NormType.DFL,
            'DL': NormType.DL,
            'RESOLUCION': NormType.RESOLUCION,
            'RESOLUCIÓN': NormType.RESOLUCION,
        }

        for key, tipo in tipo_map.items():
            if key in tipo_texto.upper():
                query = query.filter(Norm.tipo == tipo)
                break

        if año:
            query = query.filter(Norm.año == año)

        return query.first()

    def get_all_norms(self) -> List[Norm]:
        """Obtener todas las normas."""
        return self.session.query(Norm).all()

    def get_norms_by_tipo(self, tipo: NormType) -> List[Norm]:
        """Obtener normas por tipo."""
        return self.session.query(Norm).filter(Norm.tipo == tipo).all()

    def get_norms_by_año(self, año: int) -> List[Norm]:
        """Obtener normas por año."""
        return self.session.query(Norm).filter(Norm.año == año).all()

    def get_norms_by_organismo(self, organismo: str) -> List[Norm]:
        """Obtener normas por organismo."""
        return self.session.query(Norm).filter(
            Norm.organismo_normalizado == organismo
        ).all()

    def get_norms_count(self) -> int:
        """Contar total de normas."""
        return self.session.query(func.count(Norm.id)).scalar()

    def get_derogadas(self) -> List[Norm]:
        """Obtener normas derogadas."""
        return self.session.query(Norm).filter(
            Norm.estado == NormStatus.DEROGADA
        ).all()

    # --- CRUD Relaciones ---

    def add_relationship(self, rel: NormRelationship) -> NormRelationship:
        """Agregar una relación."""
        self.session.add(rel)
        self.session.commit()
        return rel

    def add_relationships_bulk(self, rels: List[NormRelationship]) -> int:
        """Agregar múltiples relaciones."""
        self.session.add_all(rels)
        self.session.commit()
        return len(rels)

    def get_relationship_exists(
        self,
        source_id: int,
        target_id: int,
        rel_type: RelationshipType
    ) -> bool:
        """Verificar si existe una relación."""
        return self.session.query(NormRelationship).filter(
            NormRelationship.source_norm_id == source_id,
            NormRelationship.target_norm_id == target_id,
            NormRelationship.relationship_type == rel_type
        ).first() is not None

    def get_all_relationships(self) -> List[NormRelationship]:
        """Obtener todas las relaciones."""
        return self.session.query(NormRelationship).all()

    def get_relationships_by_type(self, rel_type: RelationshipType) -> List[NormRelationship]:
        """Obtener relaciones por tipo."""
        return self.session.query(NormRelationship).filter(
            NormRelationship.relationship_type == rel_type
        ).all()

    def get_modifications_to(self, norm_id: int) -> List[NormRelationship]:
        """Obtener todas las normas que modifican a una norma."""
        return self.session.query(NormRelationship).filter(
            NormRelationship.target_norm_id == norm_id,
            NormRelationship.relationship_type == RelationshipType.MODIFICA
        ).all()

    def get_modifications_by(self, norm_id: int) -> List[NormRelationship]:
        """Obtener todas las normas que una norma modifica."""
        return self.session.query(NormRelationship).filter(
            NormRelationship.source_norm_id == norm_id,
            NormRelationship.relationship_type == RelationshipType.MODIFICA
        ).all()

    def get_relationships_count(self) -> int:
        """Contar total de relaciones."""
        return self.session.query(func.count(NormRelationship.id)).scalar()

    # --- Estadísticas ---

    def get_stats(self) -> dict:
        """Obtener estadísticas de la base de datos."""
        return {
            'total_norms': self.get_norms_count(),
            'total_relationships': self.get_relationships_count(),
            'by_type': {
                tipo.value: self.session.query(func.count(Norm.id)).filter(
                    Norm.tipo == tipo
                ).scalar()
                for tipo in NormType
            },
            'by_status': {
                status.value: self.session.query(func.count(Norm.id)).filter(
                    Norm.estado == status
                ).scalar()
                for status in NormStatus
            },
            'by_relationship': {
                rel.value: self.session.query(func.count(NormRelationship.id)).filter(
                    NormRelationship.relationship_type == rel
                ).scalar()
                for rel in RelationshipType
            }
        }

    # --- Utilidades ---

    def commit(self):
        """Confirmar transacción."""
        self.session.commit()

    def rollback(self):
        """Revertir transacción."""
        self.session.rollback()
