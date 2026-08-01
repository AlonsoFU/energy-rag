"""A/B retrieval: BM25+Qwen (actual) vs BM25+e5 (reemplazo) vs BM25+Qwen+e5+bgem3 (4-patas).
gold∈top10 sobre coloquial/dev/holdout. e5 con prefijos query:/passage:."""
import json
from sentence_transformers import SentenceTransformer
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion,_length_weights
from src.storage.connection import with_connection
from psycopg.rows import dict_row
SETS={'coloquial':('data/eval/queries_coloquial_v2.jsonl',{'cx_coloquial'}),
      'dev':('data/eval/queries_independent.jsonl',None),'holdout':('data/eval/queries_holdout.jsonl',None)}
store=PostgresStore(); rr=get_reranker()
qwen=Qwen3Embedder()
e5=SentenceTransformer('intfloat/multilingual-e5-large',device='cuda'); e5.max_seq_length=512
def vcol(col,qv,top_k=50):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT f.id,f.articulo_id,f.contextual_text,a.id_norma,a.numero AS articulo_numero,
            1-(f.{col} <=> %s::vector) AS score FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id
            WHERE f.{col} IS NOT NULL ORDER BY f.{col} <=> %s::vector LIMIT %s""",(qv,qv,top_k))
        return cur.fetchall()
def load(p,cats):
    out=[]
    for l in open(p):
        d=json.loads(l)
        if not d.get('expected_norma') or (cats and d.get('category') not in cats): continue
        g={tuple(x.split('/',1)) for x in [str(d['expected_norma'])+'/'+str(d['expected_articulo'])]+(d.get('also_gold') or [])}
        out.append((d['query'],g))
    return out
def hit(q,golds,mode):
    bm=store.search_bm25(q,top_k=50)
    qv=qwen.embed([q])[0]; ev=e5.encode(['query: '+q],normalize_embeddings=True)[0].tolist()
    if mode=='qwen': legs=[bm,store.search_vector(qv,50)]
    elif mode=='e5': legs=[bm,vcol('embedding_e5',ev,50)]
    else: legs=[bm,store.search_vector(qv,50),vcol('embedding_e5',ev,50),vcol('embedding_bgem3',e5.encode(['query: '+q],normalize_embeddings=True)[0].tolist() if False else qv,50)]
    w=_length_weights(q)+[1.0]*(len(legs)-2)
    fused=rrf_fusion(legs,k=60,weights=w)[:50]
    sc=rr.rerank(q,[c['contextual_text'] for c in fused],top_k=30); order=[fused[i] for i,_ in sc]
    return any((str(c.get('id_norma')),str(c.get('articulo_numero'))) in golds for c in order[:10])
for name,(p,cats) in SETS.items():
    items=load(p,cats); res={}
    for mode in ('qwen','e5'):
        res[mode]=sum(hit(q,g,mode) for q,g in items)
    print(f"{name:9s} (n={len(items)}): Qwen {res['qwen']} -> e5 {res['e5']}")
