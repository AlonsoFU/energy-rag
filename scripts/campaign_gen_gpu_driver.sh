#!/usr/bin/env bash
# Eval de generación completa en GPU (BGE fp16 cuda + 9b) sobre los 3 sets.
# Config: máxima calidad (9b) + BGE en GPU. Confirma cita_ok y que fp16 no regresa.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python
LOG=data/eval/results/campaign/gen_gpu.log
mkdir -p data/eval/results/campaign
echo "=== gen_gpu inicio $(date) ===" >> "$LOG"

export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cuda BGE_FP16=1 EMBEDDER_DEVICE=cpu TOP_RERANK_OVERRIDE=30

for pair in "GPU_gen_dev data/eval/queries_independent.jsonl" \
            "GPU_gen_holdout data/eval/queries_holdout.jsonl" \
            "GPU_gen_extremo data/eval/queries_extreme.jsonl"; do
  set -- $pair; label=$1; set=$2
  echo "=== $(date +%H:%M) ${label} (BGE fp16 GPU, top_k=10) ===" >> "$LOG"
  timeout 3000 $PY -m scripts.campaign_generation_eval "$label" "$set" 10 >> "$LOG" 2>&1
  echo "--- ${label} rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== gen_gpu FIN $(date) ===" >> "$LOG"
