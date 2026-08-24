#!/bin/bash
# Cola autonoma: gen12 (hibrido) -> reporte -> GEN2 self-consistency -> reporte -> resumen.
# Cada paso escribe en docs/resultados-auto.md, asi que los numeros quedan aunque no haya sesion.
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
ENVP="env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin \
  HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub \
  TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1 BGE_DEVICE=cuda PYTHONPATH=."

# 1) esperar al hibrido que ya corre
while pgrep -f 'scripts.exp_genflag_paired' > /dev/null; do sleep 60; done
echo "[q3] gen12 (hibrido) termino $(date '+%F %T')"
$ENVP venv/bin/python -m scripts.auto_report gen12_hybrid \
  "HIBRIDO think: intento 0 con think=True; si rechaza o no deja cita valida, reintenta con think=False." \
  >> logs/q3_report.log 2>&1

# 2) GEN2 self-consistency (N=3)
echo "[q3] lanzo GEN2 self-consistency $(date '+%F %T')"
$ENVP FLAG=self_consistency_n NAME=gen2_selfcons OFF_VAL=0 ON_VAL=3 \
  venv/bin/python -m scripts.exp_genflag_paired >> logs/gen2.log 2>&1
echo "[q3] GEN2 termino $(date '+%F %T')"
$ENVP venv/bin/python -m scripts.auto_report gen2_selfcons \
  "GEN2 self-consistency N=3: se queda con la respuesta que mas respalda el consenso de citas (>=2 de 3)." \
  >> logs/q3_report.log 2>&1

echo "[q3] TODO LISTO $(date '+%F %T'). Resultados en docs/resultados-auto.md"
