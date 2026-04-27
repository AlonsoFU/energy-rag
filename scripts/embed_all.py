"""Run the full ingest pipeline (chunk → contextual → embed → store) over
all articulos already in Postgres. Idempotent on re-runs."""
import argparse
from psycopg.rows import dict_row

from src.components.vectorstore import PostgresStore
from src.components.chunker import HierarchicalChunker
from src.components.contextual import ContextualEnricher
from src.pipelines.ingest import IngestPipeline
from src.core.models import Norma, Articulo
from src.storage.connection import with_connection


class _MockEmbedder:
    """Deterministic 1024-dim embedder for dev/tests; no model download."""
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[(hash(t + str(i)) % 1000) / 1000.0 for i in range(1024)] for t in texts]


class _NoOpEnricher:
    """Bypasses Contextual Retrieval when --skip-contextual."""
    def enrich(self, *, norma_titulo, articulo_numero, fragment_text):
        return fragment_text


def run_embed_all(skip_contextual: bool = False, mock: bool = False, limit: int | None = None) -> dict:
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

    pipeline = IngestPipeline(store=store, embedder=embedder, enricher=enricher,
                              chunker=HierarchicalChunker())

    sql = """SELECT a.*, n.titulo AS norma_titulo
             FROM articulos a JOIN normas n ON n.id_norma = a.id_norma
             ORDER BY a.id"""
    if limit:
        sql += f" LIMIT {limit}"

    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    stats = {"articulos_processed": 0, "fragmentos_created": 0}
    for i, row in enumerate(rows, 1):
        n = Norma(id_norma=row["id_norma"], tipo="X", numero="X", titulo=row["norma_titulo"])
        a = Articulo(
            id=row["id"], id_norma=row["id_norma"],
            numero=row["numero"], texto=row["texto"], orden=row["orden"],
        )
        # Count chunks BEFORE the call so the stat is accurate
        chunks = pipeline.chunker.chunk(a.texto)
        pipeline.ingest_articulo(a, n)
        stats["articulos_processed"] += 1
        stats["fragmentos_created"] += len(chunks)

        if i % 50 == 0:
            print(f"[embed_all] processed {i}/{len(rows)}  fragmentos={stats['fragmentos_created']}")

    print(f"[embed_all] done: {stats}")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-contextual", action="store_true",
                    help="Skip Contextual Retrieval (use raw chunk text)")
    ap.add_argument("--mock", action="store_true",
                    help="Use mock embedder (deterministic, no GPU)")
    args = ap.parse_args()
    run_embed_all(skip_contextual=args.skip_contextual, mock=args.mock, limit=args.limit)


if __name__ == "__main__":
    main()
