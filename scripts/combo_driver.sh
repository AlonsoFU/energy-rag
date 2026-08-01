#!/usr/bin/env bash
# Stack candidato: gate AND + anchor cita. Eval generación coloquial+dev+holdout.
set -u; cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PY=./venv-gpu/bin/python; LOG=data/eval/results/campaign/combo.log
echo "=== combo inicio $(date) ===" > "$LOG"
export HF_HUB_OFFLINE=1 USE_BGE_RERANKER=1 BGE_DEVICE=cpu EMBEDDER_DEVICE=cpu TOP_RERANK_OVERRIDE=30 OFFTOPIC_GATE_MODE=and ANCHOR_AUTHORITATIVE_CITATION=true
for pair in "COMBO_coloquial data/eval/queries_coloquial_v2.jsonl" "COMBO_dev data/eval/queries_independent.jsonl" "COMBO_holdout data/eval/queries_holdout.jsonl"; do
  set -- $pair; echo "=== $(date +%H:%M) $1 ===" >> "$LOG"
  timeout 5400 $PY -m scripts.campaign_generation_eval "$1" "$2" 10 >> "$LOG" 2>&1
  echo "--- $1 rc=$? $(date +%H:%M) ---" >> "$LOG"
done
echo "=== combo FIN $(date) ===" >> "$LOG"
