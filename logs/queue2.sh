#!/bin/bash
# 1) no-regresion (dev/coloquial/holdout)  2) GEN8a re-run con el fix de <think>
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
bash logs/run_noreg.sh >> logs/noreg.log 2>&1
echo "[queue2] noregresion listo $(date '+%F %T')"
env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. FLAG=ollama_think NAME=gen8a_v2 \
  venv/bin/python -m scripts.exp_genflag_paired >> logs/gen8a_v2.log 2>&1
echo "[queue2] gen8a_v2 listo $(date '+%F %T')"
