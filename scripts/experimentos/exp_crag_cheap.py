"""CRAG paso 1 — ¿el retrieval BARATO (BM25+denso+BGE, SIN expansión LLM) ya resuelve?
Por query: gold∈top10 (barato) + max_bge. Clasifica por bandas de BGE:
  ALTO (>=A) -> responder directo (skip 3 expansiones)
  BAJO (<R)  -> rechazar
  MEDIO      -> escalar a expansión
y reporta accuracy (gold∈top10) en cada banda → valida si BGE predice acierto."""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion,_length_weights
A,R=0.5,0.01
SETS=['queries_coloquial_v2','queries_complex_v2','queries_independent','queries_holdout']
e,r,store=Qwen3Embedder(),get_reranker(),PostgresStore()
def cheap(q):
    bm=store.search_bm25(q,top_k=50); vec=store.search_vector(e.embed([q])[0],top_k=50)
    fused=rrf_fusion([bm,vec],k=60,weights=_length_weights(q))[:50]
    if not fused: return [],0.0
    sc=r.rerank(q,[c['contextual_text'] for c in fused],top_k=30)
    order=[fused[i] for i,_ in sc]; return order, max((s for _,s in sc),default=0.0)
print(f"{'set':20s} {'n':>3s} | banda ALTA (responde)  MEDIA (escala)  BAJA (rechaza)")
for s in SETS:
    rows=[json.loads(l) for l in open(f'data/eval/{s}.jsonl') if l.strip() and json.loads(l).get('expected_norma')]
    hi=[0,0]; mid=[0,0]; lo=[0,0]  # [n, gold∈top10]
    for d in rows:
        gl=[str(d['expected_norma'])+'/'+str(d['expected_articulo'])]+(d.get('also_gold') or [])
        golds={tuple(x.split('/',1)) for x in gl}
        order,mb=cheap(d['query'])
        hit=any((str(c.get('id_norma')),str(c.get('articulo_numero'))) in golds for c in order[:10])
        band=hi if mb>=A else (lo if mb<R else mid)
        band[0]+=1; band[1]+=1 if hit else 0
    n=len(rows)
    print(f"{s:20s} {n:>3d} | ALTA {hi[0]:2d} (acc {hi[1]}/{hi[0] if hi[0] else 1})   MEDIA {mid[0]:2d} (acc {mid[1]}/{mid[0] if mid[0] else 1})   BAJA {lo[0]:2d} (acc {lo[1]}/{lo[0] if lo[0] else 1})")
