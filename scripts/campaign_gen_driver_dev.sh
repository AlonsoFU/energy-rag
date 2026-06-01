#!/usr/bin/env bash
# Eval de generación en DEV (queries_independent, 44q) baseline vs BGE — señal fuerte.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv/bin/python
LOG=data/eval/results/campaign/gen_driver_dev.log
SET=data/eval/queries_independent.jsonl
DEADLINE=$(date -d "+4 hours" +%s)
mkdir -p data/eval/results/campaign
echo "=== gen_driver_dev inicio $(date) ===" >> "$LOG"

wait_resources() {
  local c=0
  while true; do
    [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "DEADLINE, corto" >> "$LOG"; exit 0; }
    u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    r=$(free -m | awk '/Mem/{print $7}')
    if [ "${u:-9999}" -lt 400 ] && [ "${r:-0}" -gt 5500 ]; then c=$((c+1)); else c=0; fi
    [ "$c" -ge 10 ] && { echo "$(date +%H:%M) recursos libres (gpu=${u} ram=${r})" >> "$LOG"; return 0; }
    echo "$(date +%H:%M) esperando (gpu=${u}MiB ram=${r}MiB c=${c})" >> "$LOG"; sleep 30
  done
}

wait_resources
echo "=== $(date +%H:%M) GEN_dev_baseline ===" >> "$LOG"
timeout 3000 $PY -m scripts.campaign_generation_eval GEN_dev_baseline "$SET" 5 >> "$LOG" 2>&1
echo "--- dev_baseline rc=$? $(date +%H:%M) ---" >> "$LOG"

wait_resources
echo "=== $(date +%H:%M) GEN_dev_bge ===" >> "$LOG"
USE_BGE_RERANKER=1 TOP_RERANK_OVERRIDE=30 timeout 3000 $PY -m scripts.campaign_generation_eval GEN_dev_bge "$SET" 5 >> "$LOG" 2>&1
echo "--- dev_bge rc=$? $(date +%H:%M) ---" >> "$LOG"
echo "=== gen_driver_dev FIN $(date) ===" >> "$LOG"
