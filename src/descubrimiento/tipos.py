"""Tipos compartidos de la historia 1 (ver docs/briefs/contrato.md, seccion 3)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Publicacion:
    """Una norma tal como la entrega un listado de BCN."""
    id_norma: str
    tipo: str                 # "LEY", "DECRETO", "DFL", "DL", "RESOLUCION", ...
    numero: str
    titulo: str
    organismos: tuple[str, ...]   # texto crudo de BCN, sin normalizar
    fecha_publicacion: str | None  # ISO AAAA-MM-DD
    url: str


@dataclass(frozen=True)
class Vinculacion:
    """Norma de origen que modifica o deroga a una norma del corpus."""
    id_norma_origen: str
    id_norma_afectada: str
    relacion: str             # "modifica" | "deroga"


@dataclass(frozen=True)
class Hallazgo:
    """Una norma nueva vista por una via, antes de fusionar."""
    publicacion: Publicacion
    via: str                  # "V" | "O"
    afecta: tuple[Vinculacion, ...] = field(default_factory=tuple)
