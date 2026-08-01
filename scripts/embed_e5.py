"""Embebe el corpus con e5-large (prefijo passage:) en columna embedding_e5 (1024d).
Para A/B como reemplazo de Qwen. Reversible (DROP)."""
from sentence_transformers import SentenceTransformer
from src.storage.connection import with_connection
def main():
    with with_connection() as c, c.cursor() as cur:
        cur.execute("ALTER TABLE fragmentos ADD COLUMN IF NOT EXISTS embedding_e5 vector(1024)")
        c.commit()
        cur.execute("SELECT id, contextual_text FROM fragmentos WHERE embedding_e5 IS NULL ORDER BY id")
        rows=cur.fetchall()
    print(f"a embeber: {len(rows)}",flush=True)
    m=SentenceTransformer('intfloat/multilingual-e5-large',device='cuda'); m.max_seq_length=512
    B=16
    for i in range(0,len(rows),B):
        chunk=rows[i:i+B]
        vecs=m.encode(['passage: '+t for _,t in chunk],batch_size=B,normalize_embeddings=True,show_progress_bar=False)
        with with_connection() as c, c.cursor() as cur:
            cur.executemany("UPDATE fragmentos SET embedding_e5=%s WHERE id=%s",
                            [(str(v.tolist()),fid) for (fid,_),v in zip(chunk,vecs)])
            c.commit()
        if (i+B)%320==0: print(f"  {i+B}/{len(rows)}",flush=True)
    print("LISTO e5",flush=True)
if __name__=="__main__": main()
