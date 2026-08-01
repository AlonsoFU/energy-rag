#!/usr/bin/env bash
# Ensemble bge-m3 + gate AND: eval generación. Confirma si el +recall convierte a cita_ok.
set -u; cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python; LOG=data/eval/results/campaign/ensemble_gen.log
echo "=== ensemble_gen inicio $(date) ===" > "$LOG"
export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu OFFTOPIC_GATE_MODE=and ENSEMBLE_BGEM3=1 TOP_RERANK_OVERRIDE=30 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
for pair in "ENS_coloquial data/eval/queries_coloquial_v2.jsonl" "ENS_dev data/eval/queries_independent.jsonl" "ENS_holdout data/eval/queries_holdout.jsonl"; do
  set -- $pair; echo "=== $(date +%H:%M) $1 ensemble+AND ===" >> "$LOG"
  timeout 7200 $PY -m scripts.campaign_generation_eval "$1" "$2" 10 >> "$LOG" 2>&1
  echo "--- $1 rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== ensemble_gen FIN $(date) ===" >> "$LOG"
