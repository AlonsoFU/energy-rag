#!/usr/bin/env bash
# E3/E4 — Gate AND: eval de generación. Compara contra baselines léxicos (REF_*_off).
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python
LOG=data/eval/results/campaign/gate_and.log
echo "=== gate AND inicio $(date) ===" > "$LOG"
export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu TOP_RERANK_OVERRIDE=30 OFFTOPIC_GATE_MODE=and
for pair in "GATEAND_coloquial data/eval/queries_coloquial_v2.jsonl" \
            "GATEAND_dev data/eval/queries_independent.jsonl" \
            "GATEAND_holdout data/eval/queries_holdout.jsonl"; do
  set -- $pair; label=$1; set=$2
  echo "=== $(date +%H:%M) ${label} (gate=and) ===" >> "$LOG"
  timeout 5400 $PY -m scripts.campaign_generation_eval "$label" "$set" 10 >> "$LOG" 2>&1
  echo "--- ${label} rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== gate AND FIN $(date) ===" >> "$LOG"
