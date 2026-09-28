"""Generate Contextual Retrieval (Anthropic-style) for all fragments.

For each chunk:
  1. Call qwen3.5:9b via Ollama with norma + articulo + chunk text
  2. LLM generates 1-2 sentences of situational context
  3. UPDATE fragmentos.contextual_text = "{context}\\n\\n{text}"
  4. Re-embed the new contextual_text with Qwen3-Embedding
  5. UPDATE fragmentos.embedding

Designed to run in background. Resumable via --start-from N.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.components.contextual import ContextualEnricher
from src.components.embedder import Qwen3Embedder
from src.storage.connection import with_connection
from psycopg.rows import dict_row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-from", type=int, default=0, help="Skip first N fragments")
    ap.add_argument("--limit", type=int, default=None, help="Process at most N fragments")
    ap.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    args = ap.parse_args()

    print("Loading Qwen3-Embedding (CPU FP32)...")
    embedder = Qwen3Embedder()
    print("Loading ContextualEnricher (Ollama qwen3.5:9b)...")
    enricher = ContextualEnricher()

    # Fetch ONLY fragments without real contextual (i.e. those re-ingested by
    # SemanticChunker that kept the preamble "[Artículo N de NORMA] ..." as
    # contextual_text). The original ingest already enriched ~2,388 chunks
    # using ContextualEnricher; we only need to fill the remaining ~930.
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        query = """
            SELECT f.id AS frag_id, f.text AS frag_text,
                   a.numero AS articulo_numero,
                   n.tipo, n.numero AS norma_numero, n.titulo AS norma_titulo
            FROM fragmentos f
            JOIN articulos a ON a.id = f.articulo_id
            JOIN normas n ON n.id_norma = a.id_norma
            WHERE f.contextual_text LIKE '[Artículo%'
            ORDER BY f.id
        """
        cur.execute(query)
        rows = cur.fetchall()

    if args.start_from > 0:
        rows = rows[args.start_from:]
    if args.limit:
        rows = rows[:args.limit]

    total = len(rows)
    print(f"Fragments to process: {total}")
    print(f"Starting from offset: {args.start_from}, limit: {args.limit}")

    t0 = time.time()
    n_failed = 0

    for i, row in enumerate(rows, 1):
        try:
            # Build norma_titulo as "TIPO N° NUMERO - TITULO"
            norma_label = f"{row['tipo']} {row['norma_numero']}"
            if row['norma_titulo'] and row['norma_titulo'] != norma_label:
                norma_label = f"{norma_label} - {row['norma_titulo'][:120]}"

            contextual_text = enricher.enrich(
                norma_titulo=norma_label,
                articulo_numero=row['articulo_numero'],
                fragment_text=row['frag_text'],
            )
            embedding = embedder.embed([contextual_text])[0]

            if not args.dry_run:
                with with_connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        "UPDATE fragmentos SET contextual_text = %s, embedding = %s "
                        "WHERE id = %s",
                        (contextual_text, embedding, row['frag_id']),
                    )
                    conn.commit()
        except Exception as exc:
            n_failed += 1
            print(f"  [{i}/{total}] frag_id={row['frag_id']} FAILED: {exc}")
            continue

        if i % 20 == 0 or i == total:
            elapsed = time.time() - t0
            eta = elapsed / i * (total - i)
            print(f"  [{i}/{total}] frag_id={row['frag_id']} "
                  f"({row['tipo']} {row['norma_numero']}/{row['articulo_numero']}) "
                  f"| elapsed {elapsed:.0f}s eta {eta:.0f}s | failed {n_failed}")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"Processed: {total}, Failed: {n_failed}")


if __name__ == "__main__":
    main()
