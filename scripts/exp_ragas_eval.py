"""RAGAS paso B — corre las métricas sobre el dataset del paso A.

Corre en el venv aparte (no rompe venv-gpu):
  /home/alonso/datos/venvs/ragas/bin/python scripts/exp_ragas_eval.py \
    data/eval/results/ragas/coloquial__qwen3-30b-a3b.jsonl [...]

Judge = Ollama local (gratis). Embeddings = qwen3-embedding:4b (el de prod).
Métricas: faithfulness (alucinación fuera del contexto),
          context_precision (gold rankeado arriba), context_recall (gold cubierto).
Cruza cada métrica con cita_ok end-to-end.
"""
import json, os, sys
from pathlib import Path
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_anthropic import ChatAnthropic
from ragas import evaluate, EvaluationDataset
from ragas.run_config import RunConfig
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
)

JUDGE = os.environ.get("RAGAS_JUDGE", "qwen2.5:32b")
EMB = os.environ.get("RAGAS_EMB", "qwen3-embedding:4b")
OUT = Path("data/eval/results/ragas")


def load(f):
    rows = [json.loads(l) for l in open(f) if l.strip()]
    samples = [{
        "user_input": r["question"],
        "response": r["answer"] or " ",
        "retrieved_contexts": r["retrieved_contexts"] or [" "],
        "reference": r["reference"] or " ",
    } for r in rows]
    return rows, EvaluationDataset.from_list(samples)


def main():
    files = sys.argv[1:]
    if not files:
        sys.exit("uso: exp_ragas_eval.py <dataset.jsonl> [...]")
    if JUDGE.startswith("claude"):
        base = ChatAnthropic(model=JUDGE, temperature=0, max_tokens=2048,
                             timeout=120, max_retries=3)
    else:
        base = ChatOllama(model=JUDGE, temperature=0, num_ctx=16384)
    llm = LangchainLLMWrapper(base)
    emb = LangchainEmbeddingsWrapper(OllamaEmbeddings(model=EMB))
    metrics = [
        Faithfulness(llm=llm),
        LLMContextPrecisionWithReference(llm=llm),
        LLMContextRecall(llm=llm),
    ]
    # Ollama sirve de a 1 → concurrencia causa encolado+timeout (max_workers=1).
    # Claude API sí paralela → subir workers.
    default_w = "8" if JUDGE.startswith("claude") else "1"
    rc = RunConfig(timeout=int(os.environ.get("RAGAS_TIMEOUT", "180")),
                   max_workers=int(os.environ.get("RAGAS_WORKERS", default_w)))
    print(f"judge={JUDGE} emb={EMB} max_workers=1 timeout={rc.timeout}", flush=True)
    for f in files:
        rows, ds = load(f)
        print(f"\n=== {Path(f).name}  (n={len(rows)}) ===", flush=True)
        res = evaluate(ds, metrics=metrics, llm=llm, embeddings=emb,
                       run_config=rc, show_progress=True)
        df = res.to_pandas()
        cols = [c for c in df.columns if c in
                ("faithfulness", "llm_context_precision_with_reference", "context_recall")]
        # adjuntar cita_ok
        df["cita_ok"] = [r["cita_ok"] for r in rows]
        outp = OUT / (Path(f).stem + "__ragas.csv")
        df.to_csv(outp, index=False)
        print("  medias:", flush=True)
        for c in cols:
            print(f"    {c:40s} {df[c].mean():.3f}", flush=True)
        print(f"    {'cita_ok':40s} {df['cita_ok'].mean():.3f}", flush=True)
        # cruce: faithfulness en cita_ok=1 vs cita_ok=0
        if "faithfulness" in df:
            for v in (1, 0):
                sub = df[df["cita_ok"] == v]
                if len(sub):
                    print(f"    faithfulness|cita_ok={v}  {sub['faithfulness'].mean():.3f}  (n={len(sub)})", flush=True)
        print(f"  → {outp}", flush=True)


if __name__ == "__main__":
    main()
