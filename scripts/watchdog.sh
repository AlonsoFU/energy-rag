#!/bin/bash
# Watchdog. Cron cada 15 min.
#
# QUE HACE AHORA: relanza `trabajar.sh` si hay plan pendiente y NADA corriendo.
#
# QUE HACIA ANTES, y por que se reescribio: tenia la cola de 10 experimentos ESCRITA A MANO
# (gate_fraseos, veto_operativas, selfcons_n1...). Todos terminaron hace semanas, asi que
# desde entonces caia siempre en "cola COMPLETA, nada que hacer" -- 953 veces. No miraba el
# plan maestro, no sabia que existia `think_real`, y si ese experimento se moria NO lo
# relanzaba. Era codigo muerto informando verde.
#
# La leccion: una cola hardcodeada caduca en silencio. Esta version lee el plan, que es el
# unico registro de que falta.
#
# Pausar: touch .watchdog_off
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
LOG=logs/watchdog.log
mkdir -p logs
[ -f .watchdog_off ] && exit 0

# ya hay trabajo REAL corriendo -> no tocar nada. Nunca dos peleando la GPU.
if ps -eo args | grep -E '^[^ ]*python' | grep -qE 'scripts\.|exp_'; then exit 0; fi

docker start energy_rag_pg > /dev/null 2>&1

PEND=$(grep -v '^#' scripts/plan_maestro.txt | grep -c .)
# `grep -c` con cero coincidencias IMPRIME 0 y ademas SALE 1, asi que el `|| echo 0`
# agregaba un segundo cero: HECHAS quedaba en "0\n0" y el `-ge` moria con
# "se esperaba una expresion entera". Con la cola vacia el watchdog no comparaba nada.
HECHAS=$(sort -u logs/cola_hechas.txt 2>/dev/null | grep -c . || true)
HECHAS=${HECHAS:-0}

if [ "$HECHAS" -ge "$PEND" ]; then
  # PLAN AGOTADO NO ES EXITO. Es la maquina parada esperando que yo escriba el proximo plan,
  # y es exactamente como se perdieron 35 h entre el 02-09 07:19 y el 03-09 18:35 con los
  # tres crons en verde. Se deja una marca con hora para que se pueda MEDIR cuanto lleva
  # parada, en vez de una linea mas de "nada que hacer".
  if [ ! -f .plan_agotado ]; then
    date '+%F %T' > .plan_agotado
    echo "$(date '+%F %T') PLAN AGOTADO ($HECHAS/$PEND) -- MAQUINA OCIOSA, falta plan nuevo" >> "$LOG"
  else
    DESDE=$(cat .plan_agotado)
    MIN=$(( ( $(date +%s) - $(date -d "$DESDE" +%s) ) / 60 ))
    echo "$(date '+%F %T') PLAN AGOTADO hace $MIN min (desde $DESDE) -- MAQUINA OCIOSA" >> "$LOG"
  fi
  exit 0
fi

rm -f .plan_agotado
echo "$(date '+%F %T') nada corriendo con plan $HECHAS/$PEND -> relanzo trabajar.sh" >> "$LOG"
# trabajar.sh tiene su propio flock: si ya hay uno vivo, este sale solo.
setsid ./scripts/trabajar.sh >> logs/trabajar.log 2>&1 < /dev/null &
