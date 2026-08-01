"""Para las 13 coloquiales que fallan: ¿en qué rango cae el gold en el pipeline de
producción (AdaptiveRetriever)? Distingue retrieval-miss (coloquial) de
retrieved-pero-mal-citado/rechazado (grafo/generación). También verifica que el
artículo gold EXISTE en la DB (si no existe, rechazar es correcto)."""
import json
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.storage.connection import with_connection
from src.core import config as cfg

FAILS = [
 ("258171","79","Si yo tengo una planta de luz, ¿me pueden negar enchufarme a las líneas que ya están puestas de otra empresa?"),
 ("258171","87","¿Cada cuánto se sientan a planear qué torres nuevas hay que construir y quién lo hace?"),
 ("258171","104","¿Por cuántos años se supone que dura una torre o línea para sacar la cuenta de lo que cuesta?"),
 ("258171","118","¿Hay un tope de ganancia que les permiten cobrar a los dueños de las líneas grandes?"),
 ("258171","163","si me cortan la luz por falta de generación, ¿me devuelven plata por eso?"),
 ("250604","8º","soy chico y no le vendo electricidad a empresas ni a casas, ¿me puedo restar de todo ese sistema de reparto avisando nomás?"),
 ("250604","14","¿qué papeles y números le tengo que mandar al que coordina para que calcule cuánta energía voy a entregar y sacar?"),
 ("1149788","2º","quiero poner paneles en el techo de mi casa, ¿hay un tope de tamaño para que entre en este beneficio de inyectar a la red?"),
 ("1149788","13º","para empezar a conectar mis paneles, ¿a quién le tengo que mandar la solicitud y dónde se entrega?"),
 ("258171","212","Ese grupo que resuelve las peleas entre las empresas y el operador, ¿quién paga lo que cuesta tenerlo funcionando?"),
 ("29819","19","Si me sancionan y creo que es injusto, ¿cuánto tiempo tengo para reclamar y a dónde voy a alegar?"),
 ("258171","139","¿de quién es la culpa si los cables están viejos y peligrosos en la calle?"),
 ("202975","76","¿a quién llamo o dónde reclamo cuando se corta la luz en mi casa?"),
]

def gold_exists(n,a):
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT length(texto) FROM articulos WHERE id_norma=%s AND numero=%s",(n,a))
        r=cur.fetchone(); return r[0] if r else None

pool=cfg.settings.retrieval_pool_depth
e,r,store,llm=Qwen3Embedder(),get_reranker(),PostgresStore(),get_llm_provider()
router=AdaptiveRouter(); router.train_default()
simple=SimpleRetriever(store,e,r,top_bm25=pool,top_vector=pool,llm=llm)
complejo=ComplexRetriever(store,e,r,top_bm25=pool,top_vector=pool,llm=llm)
adaptive=AdaptiveRetriever(simple,complejo,router)

print(f"{'gold':14s} {'existe':7s} {'rama':9s} {'rank@30':8s} | query")
for n,a,q in FAILS:
    ln=gold_exists(n,a)
    branch,docs=adaptive.retrieve(q,top_k=30)
    rank=next((i+1 for i,d in enumerate(docs) if str(d.get('id_norma'))==n and str(d.get('articulo_numero'))==a),None)
    print(f"{n+'/'+a:14s} {'sí('+str(ln)+')' if ln else 'NO':7s} {branch:9s} {str(rank):8s} | {q[:46]}")
