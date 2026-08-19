#!/bin/bash
# Cadena: espera que termine gate_fraseos y arranca solo la NO-REGRESION sobre
# queries operativas. Sin esto no se puede adoptar glossary_lookup+intent_gate:
# el riesgo es que el gate dispare donde no debe y rompa lo que ya funciona.
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
E="env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin
   HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub
   TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1
   BGE_DEVICE=cuda PYTHONPATH=."

while pgrep -f "scripts.exp_lookup_paired" > /dev/null; do sleep 60; done
echo "[cadena] gate_fraseos termino $(date +%H:%M) -- arranco no-regresion" >> logs/cadena.log

docker start energy_rag_pg > /dev/null 2>&1
$E SET=data/eval/queries_operativas_v1.jsonl NAME=gate_noregresion \
  venv/bin/python -m scripts.exp_lookup_paired > logs/gate_noregresion.log 2>&1

echo "[cadena] no-regresion termino $(date +%H:%M)" >> logs/cadena.log
