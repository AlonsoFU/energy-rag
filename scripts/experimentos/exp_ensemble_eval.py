"""Ensemble 3-patas (BM25 + Qwen-denso + bge-m3-denso) via RRF vs baseline (2-patas).
Retrieval-only gold∈top10 sobre coloquial(target) + dev/holdout(no-reg). Mide si el
2do embedder complementario sube el recall sin regresión."""
import json, numpy as np
from sentence_transformers import SentenceTransformer
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion,_length_weights
from src.storage.connection import with_connection
from psycopg.rows import dict_row
SETS={'coloquial':('data/eval/queries_coloquial_v2.jsonl',{'cx_coloquial'}),
      'dev':('data/eval/queries_independent.jsonl',None),
      'holdout':('data/eval/queries_holdout.jsonl',None)}
store=PostgresStore(); rr=get_reranker()
qwen=SentenceTransformer('Qwen/Qwen3-Embedding-0.6B',device='cuda',trust_remote_code=True)
bgem3=SentenceTransformer('BAAI/bge-m3',device='cuda'); bgem3.max_seq_length=512
def vec_bgem3(qv,top_k=50):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT f.id, f.articulo_id, f.contextual_text, a.id_norma, a.numero AS articulo_numero,
                       1-(f.embedding_bgem3 <=> %s::vector) AS score FROM fragmentos f
                       JOIN articulos a ON a.id=f.articulo_id WHERE f.embedding_bgem3 IS NOT NULL
                       ORDER BY f.embedding_bgem3 <=> %s::vector LIMIT %s""",(qv,qv,top_k))
        return cur.fetchall()
def load(p,cats):
    out=[]
    for l in open(p):
        d=json.loads(l)
        if not d.get('expected_norma') or (cats and d.get('category') not in cats): continue
        g={tuple(x.split('/',1)) for x in [str(d['expected_norma'])+'/'+str(d['expected_articulo'])]+(d.get('also_gold') or [])}
        out.append((d['query'],g))
    return out
def top10(q,golds,ensemble):
    bm=store.search_bm25(q,top_k=50)
    qv=qwen.encode([q],normalize_embeddings=True)[0].tolist()
    vq=store.search_vector(qv,top_k=50)
    legs=[bm,vq]
    if ensemble:
        bv=bgem3.encode([q],normalize_embeddings=True)[0].tolist()
        legs.append(vec_bgem3(bv,50))
    fused=rrf_fusion(legs,k=60,weights=_length_weights(q)+([1.0] if ensemble else []))[:50]
    sc=rr.rerank(q,[c['contextual_text'] for c in fused],top_k=30); order=[fused[i] for i,_ in sc]
    return any((str(c.get('id_norma')),str(c.get('articulo_numero'))) in golds for c in order[:10])
for name,(p,cats) in SETS.items():
    items=load(p,cats); b=e=0
    for q,g in items:
        b+=top10(q,g,False); e+=top10(q,g,True)
    print(f"{name:9s}: baseline(2) {b}/{len(items)} -> ensemble(3) {e}/{len(items)}")
