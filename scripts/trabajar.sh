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

# CANDADO: el cron lanza esto cada 10 min. Sin flock se acumulaban workers -- medido: 9
# corriendo a la vez, todos peleando por la misma cola. Si ya hay uno, este sale en silencio.
exec 8>logs/.trabajar.lock
flock -n 8 || exit 0

# El plan maestro manda SIEMPRE. Antes esto era `cp -n` (no sobrescribe), asi que agregar
# tareas al plan NO llegaba a cola.txt: `trabajar.sh` contaba contra el plan y `runner.sh`
# leia la cola vieja -> el worker se creia incompleto para siempre, o al reves.
# Ahora se sincroniza en cada vuelta; `cola_hechas.txt` evita repetir lo ya hecho.
cp -f scripts/plan_maestro.txt scripts/cola.txt

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
