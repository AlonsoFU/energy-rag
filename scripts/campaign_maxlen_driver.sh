#!/usr/bin/env bash
# Fase 2: BGE max_length 512/1024/2048, retrieval-only, dev + extremo. Gating + background.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv/bin/python
LOG=data/eval/results/campaign/maxlen_driver.log
SETS="data/eval/queries_independent.jsonl data/eval/queries_extreme.jsonl"
DEADLINE=$(date -d "+5 hours" +%s)
mkdir -p data/eval/results/campaign
echo "=== maxlen inicio $(date) ===" >> "$LOG"

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

for ml in 512 1024 2048; do
  label="A_bge_ml${ml}"
  [ -f "data/eval/results/campaign/${label}.json" ] && { echo "skip ${label}" >> "$LOG"; continue; }
  wait_resources
  echo "=== $(date +%H:%M) ${label} (BGE rr30 max_length=${ml}) ===" >> "$LOG"
  CAMPAIGN_RERANKER=bge TOP_RERANK_OVERRIDE=30 BGE_MAX_LENGTH=$ml \
    timeout 5400 $PY -m scripts.campaign_sweep "$label" $SETS >> "$LOG" 2>&1
  echo "--- ${label} rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== maxlen FIN $(date) ===" >> "$LOG"
