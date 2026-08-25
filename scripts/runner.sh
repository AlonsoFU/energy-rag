#!/bin/bash
# Runner de la cola -- cron cada hora.
#
# Por que existe: el latido solo REGISTRA. El 25-08 quedaron 7 horas de "CORRIENDO" con la GPU
# en 0% porque nadie relanzaba trabajo -- el latido contaba loops de espera de bash como si
# fueran trabajo, y no habia nada que tomara la siguiente tarea.
#
# Si hay python trabajando, no toca nada. Si no hay, toma la primera tarea pendiente de
# scripts/cola.txt y la lanza. Una a la vez: nunca dos peleando la GPU.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
mkdir -p logs
LOG=logs/runner.log
HECHAS=logs/cola_hechas.txt
touch "$HECHAS"

[ -f .watchdog_off ] && exit 0

# ¿ya hay trabajo REAL corriendo? (solo procesos python, no loops de espera)
if ps -eo args | grep -E '^[^ ]*python' | grep -qE 'scripts\.|exp_'; then
  exit 0
fi

while IFS='|' read -r etiqueta cmd; do
  case "$etiqueta" in ''|\#*) continue ;; esac
  grep -qxF "$etiqueta" "$HECHAS" && continue
  echo "$(date '+%F %T')  LANZO $etiqueta" >> "$LOG"
  if eval "$cmd" >> "logs/cola_$etiqueta.log" 2>&1; then
    echo "$etiqueta" >> "$HECHAS"
    echo "$(date '+%F %T')  OK    $etiqueta" >> "$LOG"
  else
    echo "$etiqueta" >> "$HECHAS"   # no reintentar en loop: queda el log para mirar
    echo "$(date '+%F %T')  FALLO $etiqueta (ver logs/cola_$etiqueta.log)" >> "$LOG"
  fi
  exit 0
done < scripts/cola.txt

echo "$(date '+%F %T')  cola VACIA -- nada pendiente" >> "$LOG"
