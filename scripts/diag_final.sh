#!/bin/bash
# RES = la corrida dev que representa el estado FINAL del corpus tras gate_69a.
if grep -q "SE QUEDA" logs/cola_gate_69a.log; then RES=data/eval/results/l69_dev/result.json
else RES=data/eval/results/sc1_dev/result.json; fi
echo "diag sobre $RES"
env PYTHONPATH=. HF_HUB_OFFLINE=1 HF_HOME=/home/alonso/datos/hf SET=data/eval/queries_operativas_v1.jsonl RES=$RES venv/bin/python -m scripts.diag_donde_falla \
  && env PYTHONPATH=. venv/bin/python -m scripts.preparar_techo
