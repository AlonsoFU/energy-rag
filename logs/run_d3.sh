#!/bin/bash
# D3: trigger ampliado. Brazo OFF = tabla vieja (713), ON = nueva (743) via swap.
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
exec env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. BAK=fragmentos_definicion_bak2 \
  venv/bin/python -m scripts.exp_d2_paired
