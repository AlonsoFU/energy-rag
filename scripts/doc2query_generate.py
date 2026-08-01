"""E6 — doc2query español: genera N preguntas probables por fragmento (mT5) y las
guarda en fragmentos.doc2query_text. La columna generada tsv_aug = tsvector de
(contextual_text || doc2query_text) → "despierta" BM25 para fraseo coloquial.
Aísla el efecto a la pata BM25 (no toca contextual_text que usa el reranker, ni
los vectores). Reversible: DROP de las columnas.

Uso: HF_HUB_OFFLINE=1 EMBEDDER_DEVICE=cuda ./venv-gpu/bin/python -m scripts.doc2query_generate [N]
"""
import sys
import torch
from transformers import T5Tokenizer, MT5ForConditionalGeneration
from src.storage.connection import with_connection

MODEL = "doc2query/msmarco-spanish-mt5-base-v1"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5   # preguntas por fragmento
BATCH = 16


def ensure_columns():
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("ALTER TABLE fragmentos ADD COLUMN IF NOT EXISTS doc2query_text text")
        cur.execute("""
            ALTER TABLE fragmentos ADD COLUMN IF NOT EXISTS tsv_aug tsvector
            GENERATED ALWAYS AS (
                to_tsvector('spanish', contextual_text || ' ' || coalesce(doc2query_text, ''))
            ) STORED
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_fragmentos_tsv_aug ON fragmentos USING gin(tsv_aug)")
        conn.commit()


def main():
    ensure_columns()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = T5Tokenizer.from_pretrained(MODEL, legacy=False)
    model = MT5ForConditionalGeneration.from_pretrained(MODEL).to(dev).eval()

    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, text FROM fragmentos WHERE doc2query_text IS NULL ORDER BY id")
        rows = cur.fetchall()
    print(f"fragmentos a expandir: {len(rows)}", flush=True)

    done = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        texts = [t[:512] for _, t in chunk]
        enc = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=320).to(dev)
        with torch.no_grad():
            out = model.generate(**enc, max_length=48, do_sample=True, top_k=10,
                                 num_return_sequences=N)
        qs = tok.batch_decode(out, skip_special_tokens=True)
        # out viene aplanado: N por fragmento, en orden
        updates = []
        for j, (fid, _) in enumerate(chunk):
            block = qs[j * N:(j + 1) * N]
            joined = " ".join(dict.fromkeys(q.strip() for q in block if q.strip()))  # dedup
            updates.append((joined, fid))
        with with_connection() as conn, conn.cursor() as cur:
            cur.executemany("UPDATE fragmentos SET doc2query_text=%s WHERE id=%s", updates)
            conn.commit()
        done += len(chunk)
        if done % 320 == 0 or done == len(rows):
            print(f"  {done}/{len(rows)}  ej: {updates[0][0][:80]}", flush=True)
    print("LISTO doc2query", flush=True)


if __name__ == "__main__":
    main()
