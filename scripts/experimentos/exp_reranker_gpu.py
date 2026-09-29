"""exp #88: reranker BGE en GPU (fp32) en vez de CPU. ¿Mismo orden, cuanto mas rapido, y convive con el LLM?

Medido 2026-09-21: la busqueda tarda 21.69 s y 21.51 s son el rerank BGE, que corre en CPU por un
default de la epoca de la GTX 1080 (`reranker.py:59`). Hoy hay una RTX 3090.

Una sola pasada por query: el pipeline real llama al reranker, que puntua los MISMOS pares
(query, doc) con el modelo en CPU y en GPU; devuelve el orden de CPU (el pipeline sigue igual) y
guarda ambos. Asi se compara exactamente lo mismo, sin depender de que dos corridas coincidan.

CRITERIO, FIJADO ANTES (plan v38):
  (a) orden top-k IDENTICO CPU vs GPU en el 100 % de las llamadas a rerank (dev + held-out + 16 reales)
  (b) con el reranker cargado en GPU, `ollama ps` muestra qwen3:30b-a3b 100 % GPU al generar
      (si el LLM se desborda a CPU, lo que se gana buscando se pierde redactando)
  pasan ambos -> BGE en cuda pasa a ser el default.  Falla (a) -> se reportan las diferencias y
  NO se adopta sin medir generacion.  Falla (b) -> no se adopta.
Salida: data/eval/results/reranker_gpu.json
"""
import json, os, statistics as st, subprocess, time
from src.core import config as cfg
from src.components.embedder import Qwen3Embedder
from src.components.reranker import BGEReranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines import retrieve as R

SETS = ["data/eval/queries_operativas_v1.jsonl", "data/eval/queries_fraseos_v1.jsonl",
        "data/eval/queries_publicas_gold_v1.jsonl"]
os.environ["BGE_FP16"] = "0"   # ANTES de construir: __init__ lo lee; fp32 en GPU = mismos scores que CPU
cpu, gpu = BGEReranker("cpu"), BGEReranker("cuda")
LOG = []


class Doble:
    def rerank(self, query, docs, top_k):
        t0 = time.perf_counter(); a = cpu.rerank(query, docs, top_k); t1 = time.perf_counter()
        b = gpu.rerank(query, docs, top_k); t2 = time.perf_counter()
        LOG.append({"query": query, "n_docs": len(docs), "cpu": [i for i, _ in a], "gpu": [i for i, _ in b],
                    "max_dif_score": max((abs(x - y) for (_, x), (_, y) in
                                          zip(sorted(a), sorted(b))), default=0.0),
                    "s_cpu": t1 - t0, "s_gpu": t2 - t1})
        return a


cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024
llm = get_llm_provider()
retr = R.SimpleRetriever(PostgresStore(), Qwen3Embedder(), Doble(),
                         top_bm25=cfg.settings.retrieval_pool_depth,
                         top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
qs = [json.loads(l)["query"] for s in SETS for l in open(s) if l.strip()]
for i, q in enumerate(qs, 1):
    retr.retrieve(q, top_k=10)
    if i % 20 == 0:
        print(f"  [{i}/{len(qs)}]", flush=True)

dist = [x for x in LOG if x["cpu"] != x["gpu"]]
out = {"queries": len(qs), "llamadas_rerank": len(LOG), "orden_distinto": len(dist),
       "max_dif_score": max(x["max_dif_score"] for x in LOG),
       "s_cpu_media": st.mean(x["s_cpu"] for x in LOG), "s_gpu_media": st.mean(x["s_gpu"] for x in LOG),
       "diferencias": dist[:20]}

# (b) convivencia: con el BGE en GPU cargado, generar una respuesta y mirar donde quedo el LLM
llm.generate("Responde solo: ok", model="ollama/qwen3:30b-a3b", temperature=0.0, max_tokens=5)
out["ollama_ps"] = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
out["vram_mib"] = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
                                 capture_output=True, text=True).stdout.strip()
json.dump(out, open("data/eval/results/reranker_gpu.json", "w"), ensure_ascii=False, indent=1)
print({k: v for k, v in out.items() if k != "diferencias"})
