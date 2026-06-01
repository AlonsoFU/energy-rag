#!/usr/bin/env bash
# Driver de la campaña de experimentación (corre en background, gating de recursos).
# Para cada config: espera GPU/RAM libres, corre campaign_sweep, loguea resumen.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv/bin/python
LOG=data/eval/results/campaign/driver.log
DEADLINE=$(date -d "+8 hours" +%s)
mkdir -p data/eval/results/campaign
echo "=== driver inicio $(date) deadline $(date -d @${DEADLINE}) ===" >> "$LOG"

# cola: LABEL|ENVVARS (espacio-separadas)
QUEUE=(
  "E5_hyde|HYDE_IN_SIMPLE=1 EMBEDDER_DEVICE=cpu"
  "E6_hyde_rr50|HYDE_IN_SIMPLE=1 TOP_RERANK_OVERRIDE=50 EMBEDDER_DEVICE=cpu"
  "E7_pool100|RETRIEVAL_POOL_DEPTH=100"
  "E8_pool100_rr50|RETRIEVAL_POOL_DEPTH=100 TOP_RERANK_OVERRIDE=50"
  "E4_bge_rr30|CAMPAIGN_RERANKER=bge TOP_RERANK_OVERRIDE=30"
  "E9_bge_pool100_rr30|CAMPAIGN_RERANKER=bge RETRIEVAL_POOL_DEPTH=100 TOP_RERANK_OVERRIDE=30"
  "E10_hyde_bge_rr30|HYDE_IN_SIMPLE=1 CAMPAIGN_RERANKER=bge TOP_RERANK_OVERRIDE=30 EMBEDDER_DEVICE=cpu"
)

wait_resources() {
  while true; do
    [ "$(date +%s)" -ge "$DEADLINE" ] && { echo "DEADLINE alcanzado, corto" >> "$LOG"; exit 0; }
    u=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits 2>/dev/null | head -1)
    r=$(free -m | awk '/Mem/{print $7}')
    if [ "${u:-9999}" -lt 400 ] && [ "${r:-0}" -gt 5500 ]; then return 0; fi
    echo "$(date +%H:%M) esperando recursos (gpu=${u}MiB ram=${r}MiB)" >> "$LOG"
    sleep 60
  done
}

for item in "${QUEUE[@]}"; do
  label="${item%%|*}"
  envs="${item#*|}"
  out="data/eval/results/campaign/${label}.json"
  [ -f "$out" ] && { echo "skip ${label} (ya existe)" >> "$LOG"; continue; }
  wait_resources
  echo "=== $(date +%H:%M) corriendo ${label} [${envs}] ===" >> "$LOG"
  env $envs timeout 1800 $PY -m scripts.campaign_sweep "$label" >> "$LOG" 2>&1
  echo "--- ${label} rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== driver FIN $(date) ===" >> "$LOG"
