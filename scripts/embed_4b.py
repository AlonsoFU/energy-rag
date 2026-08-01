"""Re-embeber el corpus con Qwen3-Embedding-4B (GGUF vía Ollama, cabe en Pascal).

Puebla fragmentos.embedding_4b (vector 2560) con el contextual_text de cada chunk.
El embedder grande (4B) es el único salto real no probado para el coloquial; el 4-bit
GGUF de Ollama corre en la GTX 1080 (a diferencia de fp16/bitsandbytes que no caben/Pascal).

Uso: PYTHONPATH=. venv/bin/python -m scripts.embed_4b
"""
import json, urllib.request
from src.storage.connection import with_connection

MODEL = "qwen3-embedding:4b"
URL = "http://localhost:11434/api/embed"


def embed(texts):
    data = json.dumps({"model": MODEL, "input": texts}).encode()
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["embeddings"]


def main():
    with with_connection() as c, c.cursor() as cur:
        cur.execute("SELECT id, contextual_text FROM fragmentos "
                    "WHERE contextual_text IS NOT NULL AND embedding_4b IS NULL ORDER BY id")
        rows = cur.fetchall()
    total = len(rows)
    print(f"a embeber: {total}", flush=True)
    B = 16
    done = 0
    for i in range(0, total, B):
        batch = rows[i:i+B]
        embs = embed([t for _, t in batch])
        with with_connection() as c, c.cursor() as cur:
            for (fid, _), e in zip(batch, embs):
                cur.execute("UPDATE fragmentos SET embedding_4b = %s::vector WHERE id = %s",
                            (str(e), fid))
            c.commit()
        done += len(batch)
        if done % 160 == 0 or done == total:
            print(f"  {done}/{total}", flush=True)
    print("LISTO", flush=True)


if __name__ == "__main__":
    main()
