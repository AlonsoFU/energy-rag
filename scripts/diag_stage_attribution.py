"""Atribuye cada fallo a la SUB-ETAPA culpable midiendo el rank del gold en cada pata:
BM25-solo, embedder-solo, tras-fusión(RRF), tras-rerank(BGE). Query original (sin multi-query)
para aislar componentes. Pool 200."""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights

FAILS=[("258171","79"),("258171","87"),("258171","104"),("258171","118"),("258171","163"),
("250604","8º"),("250604","14"),("1149788","2º"),("1149788","13º"),("258171","212"),
("29819","19"),("258171","139"),("202975","76")]
Q={("258171","79"):"Si yo tengo una planta de luz, ¿me pueden negar enchufarme a las líneas de otra empresa?",
("258171","87"):"¿Cada cuánto se sientan a planear qué torres nuevas construir y quién lo hace?",
("258171","104"):"¿Por cuántos años dura una torre o línea para sacar la cuenta de lo que cuesta?",
("258171","118"):"¿Hay un tope de ganancia que les permiten cobrar a los dueños de las líneas grandes?",
("258171","163"):"si me cortan la luz por falta de generación, ¿me devuelven plata por eso?",
("250604","8º"):"soy chico y no le vendo electricidad a nadie, ¿me puedo restar del sistema de reparto avisando nomás?",
("250604","14"):"¿qué papeles y números le tengo que mandar al que coordina para que calcule cuánta energía entrego?",
("1149788","2º"):"quiero poner paneles en el techo de mi casa, ¿hay un tope de tamaño para este beneficio de inyectar a la red?",
("1149788","13º"):"para empezar a conectar mis paneles, ¿a quién le mando la solicitud y dónde se entrega?",
("258171","212"):"ese grupo que resuelve las peleas entre las empresas y el operador, ¿quién paga tenerlo funcionando?",
("29819","19"):"si me sancionan y creo que es injusto, ¿cuánto tiempo tengo para reclamar y a dónde voy?",
("258171","139"):"¿de quién es la culpa si los cables están viejos y peligrosos en la calle?",
("202975","76"):"¿a quién llamo o dónde reclamo cuando se corta la luz en mi casa?"}

e,r,store=Qwen3Embedder(),get_reranker(),PostgresStore()
def rankin(rows,n,a):
    return next((i+1 for i,c in enumerate(rows) if str(c.get('id_norma'))==n and str(c.get('articulo_numero'))==a),None)
# fragmentos traen id_norma/articulo? usan articulo_id->hay que mapear. Uso campos del store.
print(f"{'gold':14s} {'BM25':>5s} {'VEC':>5s} {'FUS':>5s} {'RERANK':>7s}  culpable")
for n,a in FAILS:
    q=Q[(n,a)]
    bm=store.search_bm25(q,top_k=200); vec=store.search_vector(e.embed([q])[0],top_k=200)
    rb=rankin(bm,n,a); rv=rankin(vec,n,a)
    fused=rrf_fusion([bm,vec],k=60,weights=_length_weights(q))[:200]; rf=rankin(fused,n,a)
    sc=r.rerank(q,[c['contextual_text'] for c in fused[:50]],top_k=50)
    order=[fused[i] for i,_ in sc]; rr=rankin(order,n,a)
    # atribución
    if rb is None and rv is None: cul="AMBAS PATAS ciegas (vocab)"
    elif rv and (rb is None or rv<rb): cul="embedder lo trae"+(" (BM25 ciego)" if rb is None else "")
    elif rb and (rv is None or rb<rv): cul="BM25 lo trae"+(" (embedder ciego)" if rv is None else "")
    else: cul="ambas"
    if rr and rr>10 and rf and rf<=rr: cul+=" | RERANK lo hunde"
    elif rr and rr<=10: cul+=" | rerank OK->top10"
    print(f"{n+'/'+a:14s} {str(rb):>5s} {str(rv):>5s} {str(rf):>5s} {str(rr):>7s}  {cul}")
