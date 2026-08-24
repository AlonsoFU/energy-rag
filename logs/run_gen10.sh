#!/bin/bash
# GEN10: cuantos docs ve el generador. 10 (actual) -> 5.
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. \
  FLAG=answer_doc_limit NAME=gen10_top5 OFF_VAL=0 ON_VAL=5 \
  venv/bin/python -m scripts.exp_genflag_paired
