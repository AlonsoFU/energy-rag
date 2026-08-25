#!/bin/bash
# Latido -- cron cada hora. Deja registro de si hay trabajo corriendo o si se paro.
# No decide ni relanza (de eso se encarga watchdog.sh cada 15 min): solo deja constancia,
# para poder responder "¿segui corriendo?" con un dato y no con una impresion.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
mkdir -p logs
{
  # Contar SOLO python trabajando. Antes contaba 'scripts\.' sobre toda la linea de comando,
  # asi que un `until ! pgrep -f scripts.foo; do sleep; done` -- un loop de ESPERA -- contaba
  # como trabajo. Resultado: 7 horas de "CORRIENDO procesos=3" con la GPU en 0% y 20 W.
  N=$(ps -eo args | grep -E '^[^ ]*python' | grep -cE 'scripts\.|exp_')
  W=$(nvidia-smi --query-gpu=power.draw,utilization.gpu --format=csv,noheader 2>/dev/null)
  P=$(docker inspect energy_rag_pg --format '{{.State.Status}}' 2>/dev/null)
  if [ "$N" -gt 0 ]; then
    echo "$(date '+%F %T')  CORRIENDO  procesos=$N  gpu=$W  pg=$P  :: $(ps -eo args | grep -oE '[s]cripts\.[a-z_]+' | sort -u | tr '\n' ' ')"
  else
    echo "$(date '+%F %T')  PARADO  <-- nada trabajando     gpu=$W  pg=$P  cola=$(ls data/eval/results/*/result.json 2>/dev/null | wc -l) resultados"
  fi
} >> logs/latido.log 2>&1
