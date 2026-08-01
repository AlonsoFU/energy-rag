#!/usr/bin/env bash
# Rescate near-miss/miss: pool100 + top_k15 vs baseline. Gate AND ya default.
set -u; cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python; LOG=data/eval/results/campaign/rescue.log
echo "=== rescue inicio $(date) ===" > "$LOG"
export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu OFFTOPIC_GATE_MODE=and
# config A: pool100 top_rerank 40 top_k15
export RETRIEVAL_POOL_DEPTH=100 TOP_RERANK_OVERRIDE=40
for pair in "RESCUE_coloquial data/eval/queries_coloquial_v2.jsonl 15" \
            "RESCUE_dev data/eval/queries_independent.jsonl 15" \
            "RESCUE_holdout data/eval/queries_holdout.jsonl 15"; do
  set -- $pair; echo "=== $(date +%H:%M) $1 pool100 tk15 ===" >> "$LOG"
  timeout 6000 $PY -m scripts.campaign_generation_eval "$1" "$2" "$3" >> "$LOG" 2>&1
  echo "--- $1 rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== rescue FIN $(date) ===" >> "$LOG"
