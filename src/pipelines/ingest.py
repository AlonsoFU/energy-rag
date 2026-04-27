from src.components.vectorstore import PostgresStore
from src.components.chunker import HierarchicalChunker
from src.core.models import Norma, Articulo, Fragmento, Referencia
from src.core.catalogo import Catalogo
from src.extraction.regex_refs import extract_regex_refs, ExtractedRef
from src.extraction.alias_refs import extract_alias_refs
from src.extraction.positional_refs import extract_positional_refs
from src.extraction.concept_refs import extract_concept_refs


def _to_referencia(er: ExtractedRef, fallback_origen_norma: str | None = None) -> Referencia | None:
    """Convert an ExtractedRef into a Referencia pydantic model, picking valid XOR slots.

    - Prefer origen_articulo_id if set; else origen_norma_id; else fallback_origen_norma.
    - Destino must have exactly one set; if multiple, prefer articulo_id > norma_id > concepto_id.
    Returns None if origen or destino can't be made unique.
    """
    # ORIGEN
    if er.origen_articulo_id is not None:
        origen_articulo_id, origen_norma_id = er.origen_articulo_id, None
    elif er.origen_norma_id is not None:
        origen_articulo_id, origen_norma_id = None, er.origen_norma_id
    elif fallback_origen_norma is not None:
        origen_articulo_id, origen_norma_id = None, fallback_origen_norma
    else:
        return None

    # DESTINO — exactly one
    destinations = [
        ("destino_articulo_id", er.destino_articulo_id),
        ("destino_norma_id", er.destino_norma_id),
        ("destino_concepto_id", er.destino_concepto_id),
    ]
    set_dest = [(k, v) for k, v in destinations if v is not None]
    if len(set_dest) != 1:
        return None
    dest_kwargs = {set_dest[0][0]: set_dest[0][1]}

    return Referencia(
        origen_articulo_id=origen_articulo_id,
        origen_norma_id=origen_norma_id,
        **dest_kwargs,
        tipo_relacion=er.tipo_relacion,
        confianza=er.confianza,
        metodo_extraccion=er.metodo_extraccion,
        destino_subdivision=er.destino_subdivision,
        contexto=er.contexto,
        metadata=er.metadata,
    )


class IngestPipeline:
    def __init__(
        self,
        store: PostgresStore | None = None,
        embedder=None,
        enricher=None,
        chunker: HierarchicalChunker | None = None,
        catalogo: Catalogo | None = None,
    ):
        self.store = store or PostgresStore()
        self.embedder = embedder
        self.enricher = enricher
        self.chunker = chunker or HierarchicalChunker()
        self.catalogo = catalogo

    def ingest_norma(self, norma: Norma) -> None:
        self.store.upsert_norma(norma)

    def ingest_articulo(self, articulo: Articulo, norma: Norma) -> int:
        art_id = self.store.upsert_articulo(articulo)
        chunks = self.chunker.chunk(articulo.texto)
        for ch in chunks:
            ctx_text = self.enricher.enrich(
                norma_titulo=norma.titulo,
                articulo_numero=articulo.numero,
                fragment_text=ch.text,
            )
            embedding = self.embedder.embed([ctx_text])[0]
            self.store.upsert_fragmento(Fragmento(
                articulo_id=art_id,
                chunk_index=ch.chunk_index,
                text=ch.text,
                contextual_text=ctx_text,
                embedding=embedding,
                token_count=ch.token_count,
            ))
        return art_id

    def extract_references_for_articulo(
        self,
        articulo_id: int,
        articulo_text: str,
        origen_norma_id: str,
        siblings: list[dict],
        conceptos: list[dict],
    ) -> int:
        if not self.catalogo:
            return 0

        all_extracted: list[ExtractedRef] = []

        # regex_refs and alias_refs don't take origen — we'll add it in conversion
        for er in extract_regex_refs(articulo_text, self.catalogo):
            er.origen_articulo_id = articulo_id  # mutate to set origen
            all_extracted.append(er)
        for er in extract_alias_refs(articulo_text, self.catalogo):
            er.origen_articulo_id = articulo_id
            all_extracted.append(er)

        # positional_refs takes origen explicitly
        all_extracted += extract_positional_refs(
            articulo_text, articulo_id, origen_norma_id, siblings,
        )

        # concept_refs takes origen explicitly
        all_extracted += extract_concept_refs(
            articulo_text, articulo_id, origen_norma_id, conceptos,
        )

        count = 0
        for er in all_extracted:
            ref = _to_referencia(er, fallback_origen_norma=origen_norma_id)
            if ref is None:
                continue
            try:
                self.store.upsert_referencia(ref)
                count += 1
            except Exception:
                # Skip refs that violate constraints (e.g., self-reference or destino_norma not in DB)
                continue
        return count
