#!/bin/bash
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. \
  SET_PATH=data/eval/queries_balanced_v2_clean.jsonl OUTNAME=e0_clean_v2 \
  venv/bin/python -m scripts.exp_e0_baseline
