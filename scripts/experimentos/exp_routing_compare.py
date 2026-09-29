"""Compara triggers de routing a ESCALA: ¿qué señal predice mejor "el retrieval barato
falló → escalar"? Sobre set grande. Señales por query (todas baratas):
  B-abs    : bge_max < tau         (mi version, umbral absoluto = fragil a escala)
  B-margin : (bge1 - bge2) < tau   (relativo, scale-robusto)
  A-feat   : query larga/multiclausula (Adaptive-RAG style, pre-retrieval)
Target = cheap_miss (gold NO en top10 barato). Reporta recall de misses y costo (% escala).
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion,_length_weights
SETS=['queries_balanced_v2','queries_independent','queries_holdout','queries_coloquial_v2','queries_complex_v2','queries_complex_v3']
e,r,store=Qwen3Embedder(),get_reranker(),PostgresStore()
def cheap(q):
    bm=store.search_bm25(q,top_k=50); vec=store.search_vector(e.embed([q])[0],top_k=50)
    fused=rrf_fusion([bm,vec],k=60,weights=_length_weights(q))[:50]
    if not fused: return [],0.0,0.0
    sc=r.rerank(q,[c['contextual_text'] for c in fused],top_k=30)
    order=[fused[i] for i,_ in sc]; sval=[s for _,s in sc]
    b1=sval[0] if sval else 0.0; b2=sval[1] if len(sval)>1 else 0.0
    return order,b1,b1-b2
data=[]
for s in SETS:
    for l in open(f'data/eval/{s}.jsonl'):
        d=json.loads(l)
        if not d.get('expected_norma'): continue
        gl=[str(d['expected_norma'])+'/'+str(d['expected_articulo'])]+(d.get('also_gold') or [])
        golds={tuple(x.split('/',1)) for x in gl}
        order,bmax,bmarg=cheap(d['query'])
        hit=any((str(c.get('id_norma')),str(c.get('articulo_numero'))) in golds for c in order[:10])
        nwords=len([w for w in d['query'].split() if len(w)>3])
        data.append((hit,bmax,bmarg,nwords))
N=len(data); miss=[d for d in data if not d[0]]; nmiss=len(miss)
print(f"set grande: {N} queries, cheap_miss={nmiss} ({100*nmiss//N}%)\n")
print("trigger              umbral   escala%(costo)  recall_miss(capta los que fallan)")
def evaltrig(name, fn, taus):
    for t in taus:
        esc=[d for d in data if fn(d,t)]
        capt=[d for d in esc if not d[0]]
        cost=100*len(esc)//N; rec=100*len(capt)//nmiss if nmiss else 0
        print(f"{name:18s} {t:>6} {len(esc):4d}/{N} ({cost:2d}%)     {len(capt):3d}/{nmiss} ({rec:2d}%)")
evaltrig("B-abs bge<t", lambda d,t: d[1]<t, [0.3,0.5,0.7])
evaltrig("B-margin <t", lambda d,t: d[2]<t, [0.3,0.5,0.7])
evaltrig("A-feat words>t", lambda d,t: d[3]>t, [6,8,10])
