"""Ensemble retrieval end-to-end (cita_ok), checkpointeado. Unión N-vías por RRF:
   original + alias(mano) + glosario(concepto nearest) + rewrite(9b). BGE rerank. Gen 30b-a3b.
Uso: HF_HUB_OFFLINE=0 BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_ensemble_e2e <set.jsonl> [modo]
   modo: base (solo original) | ens (ensemble). Escribe data/eval/results/ensemble_e2e/<set>__<modo>.json (resume)."""
import json, sys, urllib.request, numpy as np
from pathlib import Path
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.components.vectorstore import PostgresStore
from src.components.reranker import get_reranker
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import rrf_fusion
from src.pipelines.alias_map import apply_alias, fires
from src.pipelines.generate import generate_answer
from scripts.exp_gen_bakeoff import _ok, _golds
import os
OLL="http://localhost:11434"; RWM="qwen3.5:9b"; GENM="ollama/"+os.environ.get("GEN_MODEL","qwen3:30b-a3b")
SETF=sys.argv[1]; MODE=sys.argv[2] if len(sys.argv)>2 else "ens"
OUT=Path("data/eval/results/ensemble_e2e"); OUT.mkdir(parents=True,exist_ok=True)
CK=OUT/(Path(SETF).stem+"__"+MODE+"__"+os.environ.get("RETR","4b")+"__"+os.environ.get("GEN_MODEL","30b").replace(":","-").replace(".","")+".json")
done=json.loads(CK.read_text()) if CK.exists() else {}
def gen9(p):
    try:
        b=json.dumps({"model":RWM,"prompt":p+" /no_think","think":False,"stream":False,"options":{"num_ctx":2048,"temperature":0}}).encode()
        t=json.loads(urllib.request.urlopen(urllib.request.Request(OLL+"/api/generate",b,{"Content-Type":"application/json"}),timeout=60).read())["response"]
        return t.split("</think>")[-1].strip() if "</think>" in t else t.strip()
    except Exception: return None
RETR=os.environ.get("RETR","4b")  # 4b (embedding_4b_1024) | 8b (embedding_8b)
def _embfull(model,text):
    b=json.dumps({"model":model,"input":text}).encode()
    return json.loads(urllib.request.urlopen(urllib.request.Request(OLL+"/api/embed",b,{"Content-Type":"application/json"}),timeout=60).read())["embeddings"][0]
def emb(text): return _embfull("qwen3-embedding:4b",text)[:1024]
def vsearch(text,store,top_k=50):
    if RETR=="8b": return store.search_vector_8b(_embfull("qwen3-embedding:8b",text), top_k=top_k)
    return store.search_vector_4b_1024(emb(text), top_k=top_k)
RW="Reformula a lenguaje juridico electrico chileno. SOLO 1-2 terminos legales, sin explicar, sin numeros.\nPregunta: "
rows=[json.loads(l) for l in open(SETF) if l.strip()]; rows=[q for q in rows if q.get("expected_norma")]
store=PostgresStore(); llm=get_llm_provider(); RR=get_reranker()  # BGE rerank sobre el pool enriquecido
with with_connection() as conn, conn.cursor(row_factory=dict_row) as c:
    c.execute("SELECT nombre FROM conceptos WHERE nombre IS NOT NULL"); terms=[x['nombre'] for x in c.fetchall()]
T=np.array([emb(t) for t in terms]) if MODE=="ens" else None
print(f"glosario {'ok' if MODE=='ens' else 'skip(base)'}, modo={MODE}, faltan {len(rows)-len(done)}",flush=True)
def near(qv):
    qv=np.array(qv); s=T@qv/(np.linalg.norm(T,axis=1)*np.linalg.norm(qv)+1e-9); return terms[int(s.argmax())]
def vs(text): return vsearch(text, store, top_k=50)
for i,q in enumerate(rows):
    key=q["query"]
    if key in done: continue
    rankings=[vs(key)]
    if MODE=="ens":
        if fires(key): rankings.append(vs(apply_alias(key)))
        rankings.append(vs(near(emb(key))))
        rw=gen9(RW+key)
        if rw: rankings.append(vs(rw))
    fused=rrf_fusion(rankings,k=60) if len(rankings)>1 else rankings[0]
    pool=fused[:50]
    texts=[(d.get("contextual_text") or d.get("text") or "") for d in pool]
    ranked=RR.rerank(key, texts, top_k=10)
    docs=[pool[i] for i,_ in ranked] if ranked else pool[:10]
    for dd in docs:
        dd.setdefault("articulo_text", dd.get("contextual_text") or dd.get("text") or "")
    try:
        ok=_ok(generate_answer(key,docs,llm=llm,model=GENM), set(_golds(q)))
    except Exception as ex:
        print(f"  {i+1}/{len(rows)} GEN-FAIL(skip) {str(ex)[:50]}",flush=True); ok=0
    done[key]=int(ok); CK.write_text(json.dumps(done,ensure_ascii=False))
    print(f"  {i+1}/{len(rows)} ok={ok} cum={sum(done.values())}",flush=True)
print(f"\n{Path(SETF).stem} [{MODE}] cita_ok = {sum(done.values())}/{len(done)}",flush=True)
