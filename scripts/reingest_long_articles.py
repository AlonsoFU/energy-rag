"""Re-ingest only the ~279 articulos >400 words using SemanticChunker.

Pipeline per article:
  1. DELETE FROM fragmentos WHERE articulo_id = X
  2. Run SemanticChunker on the article text → list[Chunk]
  3. For each chunk: build (raw_text, contextual_text_with_preamble), embed,
     INSERT into fragmentos.

The rest of the corpus (2,389 short articles) keeps its existing fragments.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.components.chunker import SemanticChunker
from src.components.embedder import Qwen3Embedder
from src.storage.connection import with_connection
from psycopg.rows import dict_row


def main():
    chunker = SemanticChunker(target_tokens=400, min_size=100, overlap_units=2)
    print("Loading Qwen3-Embedding (CPU FP32)...")
    embedder = Qwen3Embedder()

    with with_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT a.id, a.id_norma, a.numero, a.texto
                FROM articulos a
                WHERE array_length(string_to_array(a.texto, ' '), 1) > 400
                ORDER BY a.id
            """)
            long_arts = cur.fetchall()

    total = len(long_arts)
    print(f"Long articles to re-ingest: {total}")

    new_chunks_total = 0
    t0 = time.time()

    for i, art in enumerate(long_arts, 1):
        chunks = chunker.chunk(art["texto"], articulo_numero=None, id_norma=None)
        # Raw text (no preamble) and contextual_text (with preamble)
        preamble = f"[Artículo {art['numero']} de {art['id_norma']}] "
        embeddings = embedder.embed([preamble + c.text for c in chunks])

        with with_connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM fragmentos WHERE articulo_id = %s", (art["id"],))
            for c, emb in zip(chunks, embeddings):
                contextual = preamble + c.text
                cur.execute(
                    """
                    INSERT INTO fragmentos
                        (articulo_id, chunk_index, text, contextual_text,
                         embedding, token_count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (art["id"], c.chunk_index, c.text, contextual,
                     emb, c.token_count),
                )
            conn.commit()
        new_chunks_total += len(chunks)

        if i % 10 == 0 or i == total:
            elapsed = time.time() - t0
            eta = elapsed / i * (total - i)
            print(f"  [{i}/{total}] art_id={art['id']} {art['id_norma']}/{art['numero']} "
                  f"→ {len(chunks)} chunks | elapsed {elapsed:.0f}s eta {eta:.0f}s")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s")
    print(f"Total new fragments: {new_chunks_total} (was generated from {total} long articles)")


if __name__ == "__main__":
    main()
