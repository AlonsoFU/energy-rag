"""Feasibility e5-large vs Qwen vs bge-m3 sobre los golds duros (4 normas, in-memory).
e5 usa prefijos query:/passage:."""
import numpy as np
from sentence_transformers import SentenceTransformer
from src.storage.connection import with_connection
NORMS=('258171','250604','1149788','202975')
FAILS=[('258171','87'),('258171','104'),('258171','118'),('250604','14'),
('1149788','2º'),('258171','212'),('258171','139'),('202975','76')]
Q={('258171','87'):'cada cuánto planean qué torres nuevas construir y quién lo hace',
('258171','104'):'por cuántos años dura una torre o línea para sacar la cuenta de lo que cuesta',
('258171','118'):'hay un tope de ganancia que les permiten cobrar a los dueños de las líneas grandes',
('250604','14'):'qué papeles y números le mando al que coordina para que calcule cuánta energía entrego',
('1149788','2º'):'quiero poner paneles en el techo de mi casa hay un tope de tamaño para el beneficio de inyectar a la red',
('258171','212'):'ese grupo que resuelve las peleas entre las empresas y el operador quién paga tenerlo',
('258171','139'):'de quién es la culpa si los cables están viejos y peligrosos en la calle',
('202975','76'):'a quién llamo o dónde reclamo cuando se corta la luz en mi casa'}
with with_connection() as c, c.cursor() as cur:
    cur.execute("SELECT f.contextual_text, a.id_norma, a.numero FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id WHERE a.id_norma = ANY(%s)",(list(NORMS),))
    rows=cur.fetchall()
texts=[r[0] for r in rows]; keys=[(str(r[1]),str(r[2])) for r in rows]
print(f"fragmentos: {len(texts)}")
m=SentenceTransformer('intfloat/multilingual-e5-large',device='cuda'); m.max_seq_length=512
A=m.encode(['passage: '+t for t in texts],batch_size=16,normalize_embeddings=True,show_progress_bar=False)
print('=== e5-large ===')
for n,a in FAILS:
    qv=m.encode(['query: '+Q[(n,a)]],normalize_embeddings=True)[0]
    order=np.argsort(-(A@qv))
    rk=next((i+1 for i,idx in enumerate(order) if keys[idx]==(n,a)),None)
    print(f"  {n+'/'+a:13s} rank={rk}")
