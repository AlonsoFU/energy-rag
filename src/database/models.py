"""
Modelos SQLAlchemy para normas BCN del sector eléctrico.
"""

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, Enum, create_engine
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime
import enum

Base = declarative_base()


class NormType(enum.Enum):
    """Tipos de normas jurídicas chilenas."""
    LEY = "LEY"
    DECRETO = "DECRETO"
    DFL = "DFL"  # Decreto con Fuerza de Ley
    DL = "DL"    # Decreto Ley
    RESOLUCION = "RESOLUCION"
    AUTO = "AUTO"
    OTRO = "OTRO"


class NormStatus(enum.Enum):
    """Estado de vigencia de una norma."""
    VIGENTE = "VIGENTE"
    DEROGADA = "DEROGADA"
    MODIFICADA = "MODIFICADA"  # Vigente pero con modificaciones
    DESCONOCIDO = "DESCONOCIDO"


class RelationshipType(enum.Enum):
    """Tipos de relaciones entre normas."""
    MODIFICA = "MODIFICA"
    DEROGA = "DEROGA"
    DEROGA_PARCIALMENTE = "DEROGA_PARCIALMENTE"
    REGLAMENTA = "REGLAMENTA"
    COMPLEMENTA = "COMPLEMENTA"
    SUSTITUYE = "SUSTITUYE"
    AGREGA = "AGREGA"
    REFERENCIA = "REFERENCIA"


class Norm(Base):
    """Modelo para una norma jurídica."""
    __tablename__ = 'norms'

    id = Column(Integer, primary_key=True)

    # Identificación BCN
    id_norma = Column(String(50), unique=True, index=True)  # ID de BCN si existe

    # Tipo y número
    tipo = Column(Enum(NormType), nullable=False, index=True)
    numero = Column(String(50))
    tipo_texto = Column(String(200))  # Texto original: "DECRETO 62", "LEY 20936"

    # Contenido
    titulo = Column(Text, nullable=False)

    # Fechas
    fecha = Column(String(20))  # Formato original: "01-FEB-2006"
    fecha_publicacion = Column(DateTime, index=True)
    año = Column(Integer, index=True)

    # Institución
    organismo = Column(String(500))
    organismo_normalizado = Column(String(100), index=True)  # MIN_ENERGIA, CNE, SEC, etc.

    # Estado
    estado = Column(Enum(NormStatus), default=NormStatus.DESCONOCIDO, index=True)

    # Clasificación
    materias = Column(Text)  # JSON list de materias
    busqueda_original = Column(String(200))  # Término de búsqueda que lo encontró

    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones: normas que ESTA norma modifica
    modifica = relationship(
        "NormRelationship",
        foreign_keys="NormRelationship.source_norm_id",
        back_populates="source_norm",
        cascade="all, delete-orphan"
    )

    # Relaciones: normas que modifican A esta norma
    modificada_por = relationship(
        "NormRelationship",
        foreign_keys="NormRelationship.target_norm_id",
        back_populates="target_norm",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Norm {self.tipo.value} {self.numero} ({self.año})>"

    @property
    def nombre_corto(self):
        """Nombre corto para visualización."""
        if self.numero:
            return f"{self.tipo.value} {self.numero}"
        return f"{self.tipo.value} ({self.año})"


class NormRelationship(Base):
    """Relación entre dos normas (modifica, deroga, etc.)."""
    __tablename__ = 'norm_relationships'

    id = Column(Integer, primary_key=True)

    # Norma origen (la que modifica/deroga)
    source_norm_id = Column(Integer, ForeignKey('norms.id'), nullable=False, index=True)

    # Norma destino (la modificada/derogada)
    target_norm_id = Column(Integer, ForeignKey('norms.id'), nullable=False, index=True)

    # Tipo de relación
    relationship_type = Column(Enum(RelationshipType), nullable=False, index=True)

    # Detalles
    descripcion = Column(Text)  # Ej: "Modifica artículo 3"
    detectado_en = Column(String(50))  # "titulo", "texto", "vinculaciones"

    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    verificado = Column(Boolean, default=False)

    # Relaciones
    source_norm = relationship("Norm", foreign_keys=[source_norm_id], back_populates="modifica")
    target_norm = relationship("Norm", foreign_keys=[target_norm_id], back_populates="modificada_por")

    def __repr__(self):
        return f"<Relationship {self.source_norm_id} --{self.relationship_type.value}--> {self.target_norm_id}>"


def get_engine(db_path: str = "db/bcn_norms.db"):
    """Crear engine de SQLAlchemy."""
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(db_path: str = "db/bcn_norms.db"):
    """Inicializar base de datos con todas las tablas."""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Obtener sesión de base de datos."""
    Session = sessionmaker(bind=engine)
    return Session()
