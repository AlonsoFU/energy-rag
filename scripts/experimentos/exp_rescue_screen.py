"""Screen retrieval-only de las 9 fallas: ¿qué palanca sube el gold al top10/15/20?
Varía pool (50/100/200) reranqueando TODO el pool. Reporta rank final por config.
También mide un sample de dev para no-regresión gruesa."""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion,_length_weights
FAILS=[('258171','87'),('258171','104'),('258171','118'),('250604','8º'),('250604','14'),
('1149788','2º'),('258171','212'),('258171','139'),('202975','76')]
Q={('258171','87'):'¿Cada cuánto se sientan a planear qué torres nuevas hay que construir y quién lo hace?',
('258171','104'):'¿Por cuántos años se supone que dura una torre o línea para sacar la cuenta de lo que cuesta?',
('258171','118'):'¿Hay un tope de ganancia que les permiten cobrar a los dueños de las líneas grandes?',
('250604','8º'):'soy chico y no le vendo electricidad a empresas ni a casas, ¿me puedo restar del sistema de reparto avisando nomás?',
('250604','14'):'¿qué papeles y números le tengo que mandar al que coordina para que calcule cuánta energía voy a entregar?',
('1149788','2º'):'quiero poner paneles en el techo de mi casa, ¿hay un tope de tamaño para entrar en el beneficio de inyectar a la red?',
('258171','212'):'ese grupo que resuelve las peleas entre las empresas y el operador, ¿quién paga lo que cuesta tenerlo?',
('258171','139'):'¿de quién es la culpa si los cables están viejos y peligrosos en la calle?',
('202975','76'):'¿a quién llamo o dónde reclamo cuando se corta la luz en mi casa?'}
e,r,store=Qwen3Embedder(),get_reranker(),PostgresStore()
def rank_at(q,n,a,pool):
    bm=store.search_bm25(q,top_k=pool); vec=store.search_vector(e.embed([q])[0],top_k=pool)
    fused=rrf_fusion([bm,vec],k=60,weights=_length_weights(q))[:pool]
    sc=r.rerank(q,[c['contextual_text'] for c in fused],top_k=pool)
    order=[fused[i] for i,_ in sc]
    return next((i+1 for i,c in enumerate(order) if str(c.get('id_norma'))==n and str(c.get('articulo_numero'))==a),None)
print(f"{'gold':13s}  pool50  pool100  pool200")
for n,a in FAILS:
    q=Q[(n,a)]
    rs=[rank_at(q,n,a,p) for p in (50,100,200)]
    print(f"{n+'/'+a:13s}  {str(rs[0]):>5s}  {str(rs[1]):>6s}  {str(rs[2]):>6s}")
