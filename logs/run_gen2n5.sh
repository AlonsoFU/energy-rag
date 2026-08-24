#!/bin/bash
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. \
  FLAG=self_consistency_n NAME=gen2_n5 OFF_VAL=3 ON_VAL=5 \
  venv/bin/python -m scripts.exp_genflag_paired
