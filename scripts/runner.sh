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

# Los modelos NO viven en ~/.cache: estan en /home/alonso/datos (la raiz se lleno una vez con
# 253 GB de Ollama y el equipo se cayo). Sin HF_HOME, con HF_HUB_OFFLINE=1 puesto, transformers
# busca en el cache por defecto, no encuentra nada y tira
# "couldn't connect to huggingface.co ... couldn't find them in the cached files".
# Paso con act_327: el script informaba "340 -> 370 articulos" y moria al cargar el embedder,
# asi que el reemplazo nunca se aplicaba y el runner lo marcaba OK igual.
export HF_HOME=/home/alonso/datos/hf
export HF_HUB_CACHE=/home/alonso/datos/hf/hub
export TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub
export HF_HUB_OFFLINE=1

# ¿ya hay trabajo REAL corriendo? (solo procesos python, no loops de espera)
if ps -eo args | grep -E '^[^ ]*python' | grep -qE 'scripts\.|exp_'; then
  exit 0
fi

while IFS='|' read -r etiqueta cmd; do
  case "$etiqueta" in ''|\#*) continue ;; esac
  grep -qxF "$etiqueta" "$HECHAS" && continue
  # candado: evita que dos drenadores tomen la MISMA tarea a la vez
  exec 9>>logs/.runner.lock; flock -n 9 || exit 0
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
