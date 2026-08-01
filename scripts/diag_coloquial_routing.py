"""Diag retrieval-only coloquial: ¿el +6 de reform vive en SIMPLE y se pierde en COMPLEJO?
Compara gold∈top10 sobre coloquial_v2 en 3 modos: complejo-off (producción), complejo-on, simple-on.
"""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever
from src.core import config as cfg

rows=[json.loads(l) for l in open("data/eval/queries_coloquial_v2.jsonl") if l.strip()]
rows=[r for r in rows if r.get("category")=="cx_coloquial" and r.get("expected_norma")]
pool=cfg.settings.retrieval_pool_depth
e,r,store,llm=Qwen3Embedder(),get_reranker(),PostgresStore(),get_llm_provider()
simple=SimpleRetriever(store,e,r,top_bm25=pool,top_vector=pool,llm=llm)
complejo=ComplexRetriever(store,e,r,top_bm25=pool,top_vector=pool,llm=llm)

def hit(docs,golds):
    g={tuple(x.split("/",1)) for x in golds}
    return any((str(d.get("id_norma")),str(d.get("articulo_numero"))) in g for d in docs[:10])

import os
def run(tag,ret,flag):
    os.environ["SELECTIVE_REFORM"]=flag; cfg.settings.selective_reform=(flag=="1")
    n=sum(hit(ret.retrieve(x["query"],top_k=10),[f"{x['expected_norma']}/{x['expected_articulo']}"]+(x.get("also_gold")or[])) for x in rows)
    print(f"{tag}: gold∈top10 = {n}/{len(rows)}")

run("complejo OFF (producción)",complejo,"0")
run("complejo ON  (reform)    ",complejo,"1")
run("simple   ON  (reform)    ",simple,"1")
