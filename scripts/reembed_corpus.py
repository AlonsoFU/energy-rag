"""Re-embeber TODO el corpus con un embedder dado (swap de modelo, A/B).

apply = re-calcula fragmentos.embedding con el modelo dado sobre contextual_text.
Revert = correr de nuevo con el modelo Qwen original (determinista, sin backup).

Uso:
  EMBED_MODEL=BAAI/bge-m3 ./venv-gpu/bin/python -m scripts.reembed_corpus
  EMBED_MODEL=Qwen/Qwen3-Embedding-0.6B ./venv-gpu/bin/python -m scripts.reembed_corpus   # revert
El modelo se pasa por env EMBED_MODEL (o arg1). Device por EMBEDDER_DEVICE.
"""
import os
import sys
from psycopg.rows import dict_row
from src.storage.connection import with_connection
from src.components.embedder import Qwen3Embedder

MODEL = (sys.argv[1] if len(sys.argv) > 1 else None) or os.environ.get("EMBED_MODEL")


def main():
    assert MODEL, "pasá EMBED_MODEL"
    emb = Qwen3Embedder(model_name=MODEL)
    # Cap de longitud: los chunks son ~512 tokens; bge-m3 default 8192 → activación
    # gigante y OOM. 512 matchea el chunking y evita el OOM.
    try:
        emb.model.max_seq_length = int(os.environ.get("EMBED_MAXLEN", "512"))
    except Exception:
        pass
    dim = len(emb.embed(["test"])[0])
    print(f"modelo={MODEL} device={emb.device} dim={dim}")
    assert dim == 1024, f"dim {dim} != 1024 (la columna pgvector es 1024)"
    with with_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, contextual_text FROM fragmentos ORDER BY id")
        rows = cur.fetchall()
    print(f"{len(rows)} chunks a re-embeber...")
    B = int(os.environ.get("EMBED_BATCH", "16"))
    with with_connection() as conn, conn.cursor() as cur:
        for i in range(0, len(rows), B):
            batch = rows[i:i + B]
            vecs = emb.embed([r["contextual_text"] for r in batch], batch_size=B)
            for r, v in zip(batch, vecs):
                cur.execute("UPDATE fragmentos SET embedding=%s WHERE id=%s", (v, r["id"]))
            conn.commit()
            print(f"  {min(i + B, len(rows))}/{len(rows)}")
    print(f"LISTO: corpus re-embebido con {MODEL}")


if __name__ == "__main__":
    main()
