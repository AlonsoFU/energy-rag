#!/bin/bash
# E0a baseline sobre balanced_v2. Env limpio (gotcha post-reboot: env heredado rompe HF offline).
# Uso: bash logs/run_e0.sh           (run largo, RUNS=1, ~3.3h)
#      LIMIT=6 bash logs/run_e0.sh   (smoke test)
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. \
  RUNS="${RUNS:-1}" LIMIT="${LIMIT:-0}" \
  venv/bin/python -m scripts.exp_e0_baseline
