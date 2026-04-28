"""Run the full ingest pipeline (chunk → contextual → embed → store) over
all articulos already in Postgres. Idempotent on re-runs.

Also runs reference extraction (regex/alias/posicional/concept-derived) per
articulo, populating the `referencias` table — unless --skip-references is set.
"""
import argparse
from psycopg.rows import dict_row

from src.components.vectorstore import PostgresStore
from src.components.chunker import HierarchicalChunker
from src.components.contextual import ContextualEnricher
from src.pipelines.ingest import IngestPipeline
from src.core.models import Norma, Articulo
from src.core.catalogo import Catalogo, NormaEntry
from src.storage.connection import with_connection


# Hardcoded common aliases for Chilean electrical sector
# (Adapter from config/alias_normas.json's nested format is a separate TODO)
COMMON_ALIASES = {
    "DFL_4": ["LGSE", "Ley General de Servicios Eléctricos", "Ley Eléctrica"],
    "DECRETO_62": ["Reglamento de Transferencias", "Reglamento de Transferencias de Potencia"],
    "DECRETO_327": ["Reglamento de la Ley General de Servicios Eléctricos", "Reglamento Eléctrico"],
    "DECRETO_125": ["Reglamento de Coordinación", "Reglamento del Coordinador"],
    "LEY_20936": ["Ley de Transmisión", "Ley Larga de Transmisión"],
    "LEY_19940": ["Ley Corta I"],
    "LEY_20018": ["Ley Corta II"],
}


class _MockEmbedder:
    """Deterministic 1024-dim embedder for dev/tests; no model download."""
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[(hash(t + str(i)) % 1000) / 1000.0 for i in range(1024)] for t in texts]


class _NoOpEnricher:
    """Bypasses Contextual Retrieval when --skip-contextual."""
    def enrich(self, *, norma_titulo, articulo_numero, fragment_text):
        return fragment_text


def _build_catalogo_from_db(store: PostgresStore) -> Catalogo:
    """Build the Catalogo from the DB's normas table + the hardcoded common aliases."""
    db_normas = store.list_normas_for_catalogo()
    entries: list[NormaEntry] = []
    for n in db_normas:
        id_can = f"{n['tipo']}_{n['numero']}"
        variantes = Catalogo._gen_variantes(n["tipo"], n["numero"])
        entries.append(NormaEntry(
            id_canonico=id_can,
            tipo=n["tipo"],
            numero=n["numero"],
            año=n.get("año"),
            variantes=variantes,
            aliases=COMMON_ALIASES.get(id_can, []),
            titulo_oficial=n.get("titulo", "") or "",
        ))
    return Catalogo(entries)


def _fetch_siblings(id_norma: str) -> list[dict]:
    """Get all articulos of a norma in (id, orden, numero) form for positional refs."""
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, orden, numero FROM articulos WHERE id_norma=%s ORDER BY orden",
            (id_norma,)
        )
        return cur.fetchall()


def _fetch_conceptos() -> list[dict]:
    """All conceptos in (id, nombre, aliases) form for concept-derived refs."""
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, nombre, aliases FROM conceptos")
        return cur.fetchall()


def run_embed_all(
    skip_contextual: bool = False,
    mock: bool = False,
    limit: int | None = None,
    skip_references: bool = False,
) -> dict:
    store = PostgresStore()

    if mock:
        embedder = _MockEmbedder()
    else:
        from src.components.embedder import Qwen3Embedder
        embedder = Qwen3Embedder()

    if skip_contextual:
        enricher = _NoOpEnricher()
    else:
        enricher = ContextualEnricher()  # uses Mock LLM by default unless real key

    catalogo = None if skip_references else _build_catalogo_from_db(store)
    conceptos = None if skip_references else _fetch_conceptos()

    pipeline = IngestPipeline(
        store=store, embedder=embedder, enricher=enricher,
        chunker=HierarchicalChunker(), catalogo=catalogo,
    )

    sql = """SELECT a.*, n.titulo AS norma_titulo
             FROM articulos a JOIN normas n ON n.id_norma = a.id_norma
             ORDER BY a.id_norma, a.orden, a.id"""
    if limit:
        sql += f" LIMIT {limit}"

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    stats = {"articulos_processed": 0, "fragmentos_created": 0, "referencias_created": 0}

    # Cache siblings per norma to avoid re-querying
    siblings_cache: dict[str, list[dict]] = {}

    for i, row in enumerate(rows, 1):
        n = Norma(id_norma=row["id_norma"], tipo="X", numero="X", titulo=row["norma_titulo"])
        a = Articulo(
            id=row["id"], id_norma=row["id_norma"],
            numero=row["numero"], texto=row["texto"], orden=row["orden"],
        )
        # Count chunks BEFORE the call so the stat is accurate
        chunks = pipeline.chunker.chunk(a.texto)
        a_id = pipeline.ingest_articulo(a, n)
        stats["articulos_processed"] += 1
        stats["fragmentos_created"] += len(chunks)

        if not skip_references and catalogo is not None:
            if a.id_norma not in siblings_cache:
                siblings_cache[a.id_norma] = _fetch_siblings(a.id_norma)
            n_refs = pipeline.extract_references_for_articulo(
                articulo_id=a_id,
                articulo_text=a.texto,
                origen_norma_id=a.id_norma,
                siblings=siblings_cache[a.id_norma],
                conceptos=conceptos or [],
            )
            stats["referencias_created"] += n_refs

        if i % 50 == 0:
            print(
                f"[embed_all] processed {i}/{len(rows)}  "
                f"fragmentos={stats['fragmentos_created']} "
                f"referencias={stats['referencias_created']}"
            )

    print(f"[embed_all] done: {stats}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-contextual", action="store_true",
                    help="Skip Contextual Retrieval (use raw chunk text)")
    ap.add_argument("--mock", action="store_true",
                    help="Use mock embedder (deterministic, no GPU)")
    ap.add_argument("--skip-references", action="store_true",
                    help="Skip reference extraction (only chunk+embed)")
    args = ap.parse_args()
    run_embed_all(
        skip_contextual=args.skip_contextual,
        mock=args.mock,
        limit=args.limit,
        skip_references=args.skip_references,
    )


if __name__ == "__main__":
    main()
