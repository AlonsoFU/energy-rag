#!/bin/bash
# Cola: espera a que termine gen9, corre gen10 (top5) y luego gen11 (top3).
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
while pgrep -f 'scripts.exp_genflag_paired' > /dev/null; do sleep 30; done
echo "[queue] gen9 termino -> lanzo gen10 (top5) $(date '+%F %T')"
bash logs/run_gen10.sh >> logs/gen10.log 2>&1
echo "[queue] gen10 termino -> lanzo gen11 (top3) $(date '+%F %T')"
FLAG=answer_doc_limit NAME=gen11_top3 OFF_VAL=0 ON_VAL=3 \
  env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 \
  BGE_DEVICE=cuda PYTHONPATH=. FLAG=answer_doc_limit NAME=gen11_top3 OFF_VAL=0 ON_VAL=3 \
  venv/bin/python -m scripts.exp_genflag_paired >> logs/gen11.log 2>&1
echo "[queue] TODO LISTO $(date '+%F %T')"
