"""Verifica el gate AND en TODOS los sets, retrieval-only. Propiedad: AND solo afecta
queries que el LÉXICO rechaza. Para cada set cuenta: léxico-rechaza (in-domain=malo,
off-topic=ok) y de esas cuáles AND rescata (bge alto). Regresión = off-topic rescatada."""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion,_length_weights
from src.pipelines.off_topic import is_off_topic
TAU=0.01
SETS=["queries_balanced_v2","queries_balanced_v3"]
e,r,store=Qwen3Embedder(),get_reranker(),PostgresStore()
def maxbge(q):
    bm=store.search_bm25(q,top_k=50); vec=store.search_vector(e.embed([q])[0],top_k=50)
    fused=rrf_fusion([bm,vec],k=60,weights=_length_weights(q))[:50]
    if not fused: return 0.0
    sc=r.rerank(q,[c['contextual_text'] for c in fused],top_k=30)
    return max((s for _,s in sc),default=0.0)
print(f"{'set':22s} {'lex_rech_IND':12s} {'lex_rech_NEG':12s} {'rescata_IND':11s} {'REGRESA_NEG':11s}")
for s in SETS:
    rows=[json.loads(l) for l in open(f'data/eval/{s}.jsonl') if l.strip()]
    lri=lrn=resc=regr=0
    for d in rows:
        q=d['query']; indom=bool(d.get('expected_norma'))
        if not is_off_topic(q): continue   # léxico pasa → AND no cambia nada
        # léxico rechaza:
        if indom: lri+=1
        else: lrn+=1
        # AND rescata si bge>=tau
        if maxbge(q)>=TAU:
            if indom: resc+=1     # rescata in-domain = BUENO
            else: regr+=1         # rescata off-topic = REGRESIÓN
    print(f"{s:22s} {lri:^12d} {lrn:^12d} {resc:^11d} {regr:^11d}")
