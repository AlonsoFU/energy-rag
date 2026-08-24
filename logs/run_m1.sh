#!/bin/bash
# M1 pool depth 50->POOL. Env limpio (gotcha HF offline).
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. POOL="${POOL:-100}" \
  venv/bin/python -m scripts.exp_m1_pooldepth
