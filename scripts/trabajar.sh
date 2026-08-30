#!/bin/bash
# Trabaja hasta terminar el plan maestro. No para al vaciarse una tanda.
#
# Por que existe: hasta ahora yo encolaba 6 tareas, se drenaban, y el sistema quedaba PARADO
# esperando que alguien cargara la siguiente tanda. El plan maestro tiene TODO el trabajo
# pendiente; esto lo consume entero, reintenta si algo muere y se detiene solo cuando no
# queda nada.
#
# Se detiene si aparece .watchdog_off (pausa manual del usuario).
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
mkdir -p logs
LOG=logs/trabajar.log

# el plan maestro manda: si la cola quedo corta respecto al plan, se recarga
cp -n scripts/plan_maestro.txt scripts/cola.txt 2>/dev/null || true

while :; do
  [ -f .watchdog_off ] && { echo "$(date '+%F %T')  PAUSA manual (.watchdog_off)" >> "$LOG"; exit 0; }

  PEND=$(grep -v '^#' scripts/plan_maestro.txt | grep -c .)
  HECHAS=$(sort -u logs/cola_hechas.txt 2>/dev/null | grep -c . || echo 0)
  if [ "$HECHAS" -ge "$PEND" ]; then
    echo "$(date '+%F %T')  PLAN COMPLETO: $HECHAS/$PEND" >> "$LOG"
    exit 0
  fi

  # el runner toma UNA tarea; si no hay nada corriendo la lanza y espera a que termine
  ./scripts/runner.sh
  sleep 5
done
