"""exp #88b: BGE en GPU en fp16 + empty_cache. ¿Mismo orden que fp32, y deja al LLM entero en GPU?

#88: GPU-fp32 da el orden IDENTICO a CPU (194/194) pero el LLM queda 43/49 capas en GPU. fp16 usa la
mitad de VRAM (~1.1 GB vs ~2.3 GB) y `empty_cache` libera las activaciones tras cada rerank.
Referencia de orden = GPU-fp32 (ya probado identico a CPU), asi la pasada toma minutos, no horas.

CRITERIO, FIJADO ANTES (plan v39):
  (a) orden top-k fp16 IDENTICO a fp32 en el 100 % de las 194 llamadas
  (b) con el BGE fp16 cargado y usado, el LLM recien cargado queda 49/49 capas en GPU
  pasan ambos -> BGE en GPU fp16 es el default en todos los modos.
  falla (a) -> se listan las diferencias; adoptar exigiria medir generacion (no se hace aca).
  falla (b) -> no se adopta; queda solo en --buscar (fp32).
Salida: data/eval/results/reranker_fp16.json
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
subprocess.run(["ollama", "stop", "qwen3:30b-a3b"], capture_output=True)   # (b) exige carga fresca
os.environ["BGE_FP16"] = "0"; f32 = BGEReranker("cuda")
os.environ["BGE_FP16"] = "1"; f16 = BGEReranker("cuda")
LOG = []


class Doble:
    def rerank(self, query, docs, top_k):
        t0 = time.perf_counter(); a = f32.rerank(query, docs, top_k); t1 = time.perf_counter()
        b = f16.rerank(query, docs, top_k); t2 = time.perf_counter()
        LOG.append({"query": query, "f32": [i for i, _ in a], "f16": [i for i, _ in b],
                    "s_f32": t1 - t0, "s_f16": t2 - t1})
        return a


cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.embed_4b_cpu = True
llm = get_llm_provider()
retr = R.SimpleRetriever(PostgresStore(), Qwen3Embedder(), Doble(),
                         top_bm25=cfg.settings.retrieval_pool_depth,
                         top_vector=cfg.settings.retrieval_pool_depth, llm=llm)
qs = [json.loads(l)["query"] for s in SETS for l in open(s) if l.strip()]
for i, q in enumerate(qs, 1):
    retr.retrieve(q, top_k=10)
    if i % 40 == 0:
        print(f"  [{i}/{len(qs)}]", flush=True)
dist = [x for x in LOG if x["f32"] != x["f16"]]
out = {"llamadas": len(LOG), "orden_distinto": len(dist), "s_f32": st.mean(x["s_f32"] for x in LOG),
       "s_f16": st.mean(x["s_f16"] for x in LOG), "diferencias": dist[:30]}

# (b): solo queda el fp16 en GPU (como quedaria en produccion), recien usado; el LLM carga despues
import torch
del f32; torch.cuda.empty_cache()
f16.rerank(qs[0], ["texto de prueba " * 200] * 30, 10)
t_ini = time.strftime("%Y-%m-%d %H:%M:%S")
llm.generate("Responde solo: ok", model="ollama/qwen3:30b-a3b", temperature=0.0, max_tokens=5)
j = subprocess.run(["journalctl", "-u", "ollama", "--since", t_ini, "--no-pager"], capture_output=True, text=True).stdout
capas = [l.split("offloaded ")[1].split(" layers")[0] for l in j.splitlines() if "offloaded" in l and "/49" in l]
out["llm_capas_gpu"] = capas
out["ollama_ps"] = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
out["vram_mib"] = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader"],
                                 capture_output=True, text=True).stdout.strip()
json.dump(out, open("data/eval/results/reranker_fp16.json", "w"), ensure_ascii=False, indent=1)
print({k: v for k, v in out.items() if k != "diferencias"})
