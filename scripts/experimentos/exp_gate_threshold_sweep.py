"""E3 — Barrido de τ para el gate semántico (piso de score BGE).
Mide max-BGE-score por query (pipeline simple, sin Ollama). Grupos:
  POS (debe responder): coloquial_v2 + independent + holdout in-domain
  NEG (debe rechazar): negativas de independent/holdout/extreme
Reporta distribución y, para cada τ, %POS-rechazadas (malo) vs %NEG-rechazadas (bueno).
Busca el VALLE. También marca las 4 rechazadas coloquiales (163,8º,13º,19)."""
import json, statistics
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import rrf_fusion, _length_weights

def load(path, want_pos):
    out=[]
    for l in open(path):
        d=json.loads(l)
        isneg = not d.get("expected_norma")
        if want_pos and not isneg: out.append((d["query"], f"{d.get('expected_norma')}/{d.get('expected_articulo')}"))
        if (not want_pos) and isneg: out.append((d["query"], "NEG"))
    return out

POS = (load("data/eval/queries_coloquial_v2.jsonl",True)
     + load("data/eval/queries_independent.jsonl",True)
     + load("data/eval/queries_holdout.jsonl",True))
NEG = (load("data/eval/queries_independent.jsonl",False)
     + load("data/eval/queries_holdout.jsonl",False)
     + load("data/eval/queries_extreme.jsonl",False))
WATCH={"258171/163","250604/8º","1149788/13º","29819/19"}

e,r,store=Qwen3Embedder(),get_reranker(),PostgresStore()
def maxbge(q):
    bm=store.search_bm25(q,top_k=50); vec=store.search_vector(e.embed([q])[0],top_k=50)
    fused=rrf_fusion([bm,vec],k=60,weights=_length_weights(q))[:50]
    if not fused: return 0.0
    sc=r.rerank(q,[c['contextual_text'] for c in fused],top_k=30)
    return max((s for _,s in sc), default=0.0)

pos_s=[]; neg_s=[]; watch=[]
for q,g in POS:
    s=maxbge(q); pos_s.append(s)
    if g in WATCH: watch.append((g,s))
for q,g in NEG: neg_s.append(maxbge(q))

def stats(xs): 
    xs=sorted(xs); return f"min={xs[0]:.4f} p25={xs[len(xs)//4]:.4f} med={statistics.median(xs):.4f} p75={xs[3*len(xs)//4]:.4f} max={xs[-1]:.4f}"
print(f"POS (n={len(pos_s)}, deben responder): {stats(pos_s)}")
print(f"NEG (n={len(neg_s)}, deben rechazar):  {stats(neg_s)}")
print("\n4 rechazadas coloquiales (su max-BGE):")
for g,s in watch: print(f"  {g:14s} {s:.4f}")
print("\nτ      POS-rechazadas(malo)  NEG-rechazadas(bueno)")
for tau in [0.001,0.005,0.01,0.02,0.05,0.1,0.15,0.2,0.3,0.4,0.5]:
    pr=sum(1 for s in pos_s if s<tau); nr=sum(1 for s in neg_s if s<tau)
    print(f"{tau:<6} {pr:2d}/{len(pos_s)} ({100*pr//len(pos_s):2d}%)          {nr:2d}/{len(neg_s)} ({100*nr//len(neg_s):3d}%)")
