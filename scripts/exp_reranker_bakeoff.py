"""Bake-off de RERANKERS. Aísla la etapa reranker: usa el Retriever REAL de
producción (mismo pool 4b-1024 + alias + RRF + graph_boost) e inyecta cada
modelo de reranker. Mide rank del gold en la salida final (screen gold∈top5/top10).

Cubre cross-encoders (sentence-transformers) y rerankers GENERATIVOS (Qwen3-Reranker,
bge-gemma: logits yes/no) — estos últimos con loader propio (CrossEncoder les da ruido).

REGLA DE ORO: el screen MIENTE. Los ganadores del screen se confirman end-to-end
(cita_ok) en un segundo paso, no cuentan hasta entonces.

Uso: BGE_DEVICE=cuda EMBEDDER_DEVICE=cuda ./venv-gpu/bin/python -m scripts.exp_reranker_bakeoff [m1 m2 ...]
"""
import json, sys, os, time, gc
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.vectorstore import PostgresStore
from src.pipelines.retrieve import SimpleRetriever as Retriever
from src.pipelines.grounding import _normalize_art

OUTDIR = Path("data/eval/results/reranker_bakeoff")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl")]

# nombre -> (kind, hf_name, kwargs). kind: 'ce'=cross-encoder, 'qwen'=generativo yes/no, 'identity', 'bge'
MODELS = {
    "identity(control)":     ("identity", "", {}),
    "bge-v2-m3(baseline)":   ("ce", "BAAI/bge-reranker-v2-m3", {}),
    "bge-reranker-large":    ("ce", "BAAI/bge-reranker-large", {}),
    "bge-reranker-base":     ("ce", "BAAI/bge-reranker-base", {}),
    "mmarco-miniLM-es":      ("ce", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", {}),
    "jina-v2-multi":         ("ce", "jinaai/jina-reranker-v2-base-multilingual", {"trust_remote_code": True}),
    "gte-modernbert":        ("ce", "Alibaba-NLP/gte-reranker-modernbert-base", {"trust_remote_code": True}),
    "mxbai-large-v1":        ("ce", "mixedbread-ai/mxbai-rerank-large-v1", {}),
    "qwen3-rerank-0.6b":     ("qwen", "Qwen/Qwen3-Reranker-0.6B", {}),
    # --- TIER 2 (mas grandes, revisar RAM antes) ---
    "qwen3-rerank-4b":       ("qwen", "Qwen/Qwen3-Reranker-4B", {}),
    "bge-gemma2":            ("qwen", "BAAI/bge-reranker-v2-gemma", {}),
}


class CrossEncoderRR:
    def __init__(self, name, **kw):
        import torch
        from sentence_transformers import CrossEncoder
        dev = os.environ.get("BGE_DEVICE", "cuda")
        mk = {}
        if dev == "cuda" and os.environ.get("BGE_FP16", "1") == "1":
            mk["torch_dtype"] = torch.float16
        self.m = CrossEncoder(name, device=dev, max_length=512, model_kwargs=mk, **kw)

    def rerank(self, query, docs, top_k):
        if not docs:
            return []
        sc = self.m.predict([(query, d) for d in docs])
        order = sorted(range(len(docs)), key=lambda i: float(sc[i]), reverse=True)
        return [(i, float(sc[i])) for i in order[:top_k]]


class Qwen3GenRR:
    """Reranker generativo (Qwen3-Reranker / bge-gemma): prob del token 'yes' vs 'no'
    tras el prompt Instruct/Query/Document. Carga HF fp16 a GPU (0.6B safe; 4B pico RAM)."""
    PREFIX = ("<|im_start|>system\nJudge whether the Document meets the requirements "
              "based on the Query and the Instruct provided. Note that the answer can "
              "only be \"yes\" or \"no\".<|im_end|>\n<|im_start|>user\n")
    SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    TASK = "Dada una consulta, recupera el articulo legal relevante"

    def __init__(self, name):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(name, padding_side="left")
        if os.environ.get("GEN_RR_4BIT", "0") == "1":
            # 4-bit: pesos cuantizados stream directo a GPU (~modelo/4 GB), pico RAM bajo.
            from transformers import BitsAndBytesConfig
            qc = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                                    bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                name, quantization_config=qc, device_map={"": 0}, low_cpu_mem_usage=True).eval()
        else:
            mk = {"torch_dtype": torch.float16, "low_cpu_mem_usage": True}
            self.model = AutoModelForCausalLM.from_pretrained(name, **mk).to("cuda").eval()
        self.tid_yes = self.tok.convert_tokens_to_ids("yes")
        self.tid_no = self.tok.convert_tokens_to_ids("no")
        self.max_len = 1024

    def _fmt(self, q, d):
        return f"<Instruct>: {self.TASK}\n<Query>: {q}\n<Document>: {d}"

    def rerank(self, query, docs, top_k, bs=int(os.environ.get("GEN_RR_BS", "4"))):
        if not docs:
            return []
        import torch
        scores = []
        for i in range(0, len(docs), bs):
            batch = [self.PREFIX + self._fmt(query, d) + self.SUFFIX for d in docs[i:i+bs]]
            enc = self.tok(batch, return_tensors="pt", padding=True, truncation=True,
                           max_length=self.max_len).to("cuda")
            with torch.no_grad():
                logits = self.model(**enc).logits[:, -1, :]
            two = logits[:, [self.tid_no, self.tid_yes]]
            p = torch.nn.functional.log_softmax(two, dim=-1)[:, 1]  # log P(yes)
            scores.extend(p.float().cpu().tolist())
        order = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
        return [(i, float(scores[i])) for i in order[:top_k]]


def make_reranker(kind, name, kw):
    if kind == "identity":
        from src.components.reranker import IdentityReranker
        return IdentityReranker()
    if kind == "bge":
        from src.components.reranker import BGEReranker
        return BGEReranker()
    if kind == "ce":
        return CrossEncoderRR(name, **kw)
    if kind == "qwen":
        return Qwen3GenRR(name)
    raise ValueError(kind)


def load_queries():
    out = []
    for setname, path in SETS:
        for l in Path(path).read_text().splitlines():
            if not l.strip():
                continue
            q = json.loads(l)
            if q.get("expected_norma") is None:
                continue
            golds = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
            for g in q.get("also_gold") or []:
                n, a = str(g).split("/", 1); golds.add((n, _normalize_art(a)))
            out.append((setname, q["query"], golds))
    return out


def gold_rank(docs, golds):
    for i, c in enumerate(docs):
        k = (str(c.get("id_norma")), _normalize_art(str(c.get("articulo_numero"))))
        if k in golds:
            return i + 1
    return None


def main():
    names = sys.argv[1:] or [n for n in MODELS if n not in ("qwen3-rerank-4b", "bge-gemma2")]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    store, emb = PostgresStore(), Qwen3Embedder()
    queries = load_queries()
    print(f"queries={len(queries)} models={names}", flush=True)
    rj = OUTDIR / "result.json"
    res = json.loads(rj.read_text()) if rj.exists() else {}
    for nm in names:
        if nm in res:
            print(f"SKIP {nm}", flush=True); continue
        kind, hf, kw = MODELS[nm]
        t0 = time.time()
        try:
            rr = make_reranker(kind, hf, kw)
            R = Retriever(store, emb, rr, top_bm25=50, top_vector=50, top_rerank=10)
            agg = {}
            for setname, q, golds in queries:
                docs = R.retrieve(q, top_k=10)
                r = gold_rank(docs, golds)
                a = agg.setdefault(setname, {"n": 0, "top5": 0, "top10": 0})
                a["n"] += 1; a["top5"] += (r is not None and r <= 5); a["top10"] += (r is not None and r <= 10)
            res[nm] = {"agg": agg, "secs": round(time.time()-t0)}
            rj.write_text(json.dumps(res, ensure_ascii=False, indent=2))
            del rr, R; gc.collect()
            try:
                import torch; torch.cuda.empty_cache()
            except Exception:
                pass
            print(f"{nm}: " + " ".join(f"{s} t5={a['top5']}/{a['n']} t10={a['top10']}" for s, a in agg.items()) + f"  ({res[nm]['secs']}s)", flush=True)
        except Exception as ex:
            print(f"FAIL {nm}: {str(ex)[:160]}", flush=True); continue
    print("\n=== RERANKER BAKE-OFF (gold∈topN, pipeline real) ===", flush=True)
    print(f"{'modelo':22s} {'cx_t5':>6s} {'cx_t10':>7s} {'dev_t5':>7s} {'dev_t10':>8s}", flush=True)
    for nm in names:
        if nm not in res: continue
        a = res[nm]["agg"]; cx = a.get("coloquial", {}); dv = a.get("dev", {})
        print(f"{nm:22s} {cx.get('top5',0):>6d} {cx.get('top10',0):>7d} {dv.get('top5',0):>7d} {dv.get('top10',0):>8d}", flush=True)


if __name__ == "__main__":
    main()
