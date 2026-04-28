from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator

TipoNorma = Literal["LEY", "DECRETO", "DFL", "RESOLUCION", "OTROS"]
ClaseNorma = Literal["reglamento_base", "fija_valores", "modifica", "deroga"]
TipoRelacion = Literal[
    "cita", "remite", "aplica", "modifica", "deroga",
    "complementa", "define_termino", "referencia_implicita",
]
MetodoExtraccion = Literal["regex", "llm", "manual"]


class Norma(BaseModel):
    id_norma: str
    tipo: TipoNorma | str
    numero: str
    titulo: str
    fecha_publicacion: date | None = None
    organismo: str | None = None
    clase: ClaseNorma | None = None
    texto_completo: str | None = None
    metadata: dict = Field(default_factory=dict)


class Articulo(BaseModel):
    id: int | None = None
    id_norma: str
    numero: str
    titulo: str | None = None
    texto: str
    orden: int | None = None
    metadata: dict = Field(default_factory=dict)


class Fragmento(BaseModel):
    id: int | None = None
    articulo_id: int
    chunk_index: int
    text: str
    contextual_text: str
    embedding: list[float] | None = None
    token_count: int | None = None
    metadata: dict = Field(default_factory=dict)


class Concepto(BaseModel):
    id: int | None = None
    nombre: str
    definicion: str | None = None
    aliases: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class Referencia(BaseModel):
    id: int | None = None
    origen_articulo_id: int | None = None
    origen_norma_id: str | None = None
    destino_articulo_id: int | None = None
    destino_norma_id: str | None = None
    destino_concepto_id: int | None = None
    tipo_relacion: TipoRelacion
    confianza: float = Field(ge=0, le=1)
    metodo_extraccion: MetodoExtraccion
    destino_subdivision: str | None = None
    contexto: str | None = None
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _xor_origen_destino(self):
        n_origen = sum([self.origen_articulo_id is not None, self.origen_norma_id is not None])
        if n_origen != 1:
            raise ValueError("origen must be exactly one of articulo_id, norma_id")
        n_destino = sum([
            self.destino_articulo_id is not None,
            self.destino_norma_id is not None,
            self.destino_concepto_id is not None,
        ])
        if n_destino != 1:
            raise ValueError("destino must be exactly one of articulo_id, norma_id, concepto_id")
        return self
