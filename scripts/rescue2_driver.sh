#!/usr/bin/env bash
# Aislar: pool100 + top_k10 (sin dispersión de top_k15). Gate AND default.
set -u; cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python; LOG=data/eval/results/campaign/rescue2.log
echo "=== rescue2 inicio $(date) ===" > "$LOG"
export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu OFFTOPIC_GATE_MODE=and RETRIEVAL_POOL_DEPTH=100 TOP_RERANK_OVERRIDE=40
for pair in "RESCUE2_coloquial data/eval/queries_coloquial_v2.jsonl 10" \
            "RESCUE2_dev data/eval/queries_independent.jsonl 10" \
            "RESCUE2_holdout data/eval/queries_holdout.jsonl 10"; do
  set -- $pair; echo "=== $(date +%H:%M) $1 pool100 tk10 ===" >> "$LOG"
  timeout 6000 $PY -m scripts.campaign_generation_eval "$1" "$2" "$3" >> "$LOG" 2>&1
  echo "--- $1 rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== rescue2 FIN $(date) ===" >> "$LOG"
