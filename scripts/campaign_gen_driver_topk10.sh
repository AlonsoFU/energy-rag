#!/usr/bin/env bash
# Bonus: BGE + top_k=10 en holdout y dev. ¿Más recall situacional sin dispersar citas?
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv/bin/python
LOG=data/eval/results/campaign/gen_driver_topk10.log
DEADLINE=$(date -d "+3 hours" +%s)
mkdir -p data/eval/results/campaign
echo "=== topk10 inicio $(date) ===" >> "$LOG"

wait_resources() {
  local c=0
  while true; do
    [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "DEADLINE, corto" >> "$LOG"; exit 0; }
    u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    r=$(free -m | awk '/Mem/{print $7}')
    if [ "${u:-9999}" -lt 400 ] && [ "${r:-0}" -gt 5500 ]; then c=$((c+1)); else c=0; fi
    [ "$c" -ge 10 ] && { echo "$(date +%H:%M) libres (gpu=${u} ram=${r})" >> "$LOG"; return 0; }
    echo "$(date +%H:%M) esperando (gpu=${u} ram=${r} c=${c})" >> "$LOG"; sleep 30
  done
}

for pair in "GEN_holdout_bge_k10 data/eval/queries_holdout.jsonl" "GEN_dev_bge_k10 data/eval/queries_independent.jsonl"; do
  set -- $pair; label=$1; set=$2
  [ -f "data/eval/results/campaign/${label}.json" ] && { echo "skip ${label}" >> "$LOG"; continue; }
  wait_resources
  echo "=== $(date +%H:%M) ${label} (BGE, top_k=10) ===" >> "$LOG"
  USE_BGE_RERANKER=1 TOP_RERANK_OVERRIDE=30 timeout 3000 $PY -m scripts.campaign_generation_eval "$label" "$set" 10 >> "$LOG" 2>&1
  echo "--- ${label} rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== topk10 FIN $(date) ===" >> "$LOG"
