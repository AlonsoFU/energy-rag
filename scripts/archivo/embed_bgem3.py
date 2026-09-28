"""Embebe todo el corpus con bge-m3 en columna nueva fragmentos.embedding_bgem3 (1024d)
para el ensemble. Reversible (DROP). Ollama debe estar fuera de la GPU."""
import torch
from sentence_transformers import SentenceTransformer
from src.storage.connection import with_connection
def main():
    with with_connection() as c, c.cursor() as cur:
        cur.execute("ALTER TABLE fragmentos ADD COLUMN IF NOT EXISTS embedding_bgem3 vector(1024)")
        c.commit()
        cur.execute("SELECT id, contextual_text FROM fragmentos WHERE embedding_bgem3 IS NULL ORDER BY id")
        rows=cur.fetchall()
    print(f"a embeber: {len(rows)}",flush=True)
    m=SentenceTransformer('BAAI/bge-m3',device='cuda'); m.max_seq_length=512
    B=16
    for i in range(0,len(rows),B):
        chunk=rows[i:i+B]
        vecs=m.encode([t for _,t in chunk],batch_size=B,normalize_embeddings=True,show_progress_bar=False)
        with with_connection() as c, c.cursor() as cur:
            cur.executemany("UPDATE fragmentos SET embedding_bgem3=%s WHERE id=%s",
                            [(str(v.tolist()),fid) for (fid,_),v in zip(chunk,vecs)])
            c.commit()
        if (i+B)%320==0: print(f"  {i+B}/{len(rows)}",flush=True)
    print("LISTO bge-m3 embeddings",flush=True)
if __name__=="__main__": main()
