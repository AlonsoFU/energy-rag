#!/usr/bin/env bash
# FASE A — Reformulación selectiva coloquial→legal: eval de GENERACIÓN A/B.
# Corre OFF vs ON (selective_reform) sobre target=coloquial + no-reg dev/holdout.
# BGE en CPU (evita OOM con 9b en GPU). top_k=10 (producción).
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python
LOG=data/eval/results/campaign/reform_faseA.log
mkdir -p data/eval/results/campaign
echo "=== FASE A reform inicio $(date) ===" > "$LOG"

export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu TOP_RERANK_OVERRIDE=30

run () {  # label set flagval
  local label=$1 set=$2 flag=$3
  export SELECTIVE_REFORM=$flag
  echo "=== $(date +%H:%M) ${label} SELECTIVE_REFORM=${flag} (top_k=10) ===" >> "$LOG"
  timeout 5400 $PY -m scripts.campaign_generation_eval "$label" "$set" 10 >> "$LOG" 2>&1
  echo "--- ${label} rc=$? $(date +%H:%M) ---" >> "$LOG"
}

# Target primero (señal clave), luego no-regresión.
run REF_coloquial_off data/eval/queries_coloquial_v2.jsonl 0
run REF_coloquial_on  data/eval/queries_coloquial_v2.jsonl 1
run REF_dev_off       data/eval/queries_independent.jsonl  0
run REF_dev_on        data/eval/queries_independent.jsonl  1
run REF_holdout_off   data/eval/queries_holdout.jsonl      0
run REF_holdout_on    data/eval/queries_holdout.jsonl      1

echo "=== FASE A reform FIN $(date) ===" >> "$LOG"
