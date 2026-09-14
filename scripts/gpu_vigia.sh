#!/bin/bash
# VIGIA DE GPU -- cron cada minuto. Vigila la GPU MIENTRAS hay trabajo y lo corta si algo va mal.
# No reinicia nada ni toca el hardware: DETIENE la carga y deja constancia en logs/gpu_vigia.log.
#
# Corta (mata exp_*, pone .watchdog_off y .gpu_bloqueo) si:
#   - aparece un Xid 79 en este arranque (GPU fuera del bus)
#   - nvidia-smi deja de responder
#   - hay trabajo y el modelo GENERADOR de Ollama esta 100 % en CPU (size_vram = 0). El 08-09
#     paso horas asi con el CPU clavado en 95 C sin avanzar. El embedder se excluye: corre en
#     CPU a proposito (embed_4b_cpu=True) y daria falso positivo.
#   - GPU >= 88 C en 3 muestras seguidas (slowdown de la 3090 = 95 C; 88 deja margen)
#
# Limite honesto: NO previene un Xid 79. Evita lo que vino despues: relanzar sobre una GPU
# muerta, correr horas en CPU, y enterarse solo cuando el usuario escribe.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
mkdir -p logs
LOG=logs/gpu_vigia.log
TRABAJO=$(pgrep -fc '[s]cripts\.exp_' || true)

cortar(){
  { date '+%F %T'; echo "$*"; } > .gpu_bloqueo
  touch .watchdog_off
  pkill -f '[s]cripts\.exp_' 2>/dev/null
  pkill -f '[t]rabajar\.sh' 2>/dev/null
  echo "$(date '+%F %T')  CORTE: $*" >> "$LOG"
  nvidia-smi >> "$LOG" 2>&1
  exit 1
}

journalctl -k -b 0 --no-pager 2>/dev/null | grep -qE 'Xid .*: 79,|fallen off the bus' \
  && cortar "Xid 79: GPU fuera del bus"

Q=$(nvidia-smi --query-gpu=temperature.gpu,power.draw,clocks.sm --format=csv,noheader,nounits 2>&1) \
  || cortar "nvidia-smi no responde: $Q"
T=$(echo "$Q" | cut -d, -f1 | tr -d ' ')

R=$(cat logs/.gpu_vigia_racha 2>/dev/null || echo 0)
if [ "${T:-0}" -ge 88 ]; then R=$((R + 1)); else R=0; fi
echo "$R" > logs/.gpu_vigia_racha
[ "$R" -ge 3 ] && cortar "GPU a ${T} C en 3 muestras seguidas"

if [ "${TRABAJO:-0}" -gt 0 ]; then
  DONDE=$(curl -s --max-time 5 http://localhost:11434/api/ps 2>/dev/null | python3 -c '
import json, sys
try:
    ms = [m for m in json.load(sys.stdin).get("models", []) if "embed" not in m.get("name", "")]
except Exception:
    print("?"); sys.exit()
print("CPU" if any(m.get("size_vram", 0) == 0 for m in ms) else ("GPU" if ms else "NINGUNO"))
' 2>/dev/null)
  [ "$DONDE" = "CPU" ] && cortar "modelo generador de Ollama en CPU (size_vram=0) con trabajo corriendo"
  echo "$(date '+%F %T')  ok  trabajo=$TRABAJO  modelo=$DONDE  gpu(C,W,MHz)=$Q" >> "$LOG"
fi
exit 0
