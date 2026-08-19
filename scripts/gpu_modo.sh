#!/bin/bash
# Cambia el limite de potencia de la GPU segun para que la vas a usar.
#
#   ./scripts/gpu_modo.sh juego      350 W  -- FPS completos, ruidosa
#   ./scripts/gpu_modo.sh silencio   120 W  -- para evals de noche (~20% mas lento)
#   ./scripts/gpu_modo.sh            muestra el estado actual
#
# El limite NO persiste tras reiniciar: al bootear vuelve solo a 350 W.
case "${1:-}" in
  juego|game|350)     sudo nvidia-smi -pl 350 > /dev/null && echo "GPU -> 350 W (juego)";;
  silencio|quiet|120) sudo nvidia-smi -pl 120 > /dev/null && echo "GPU -> 120 W (silencio)";;
  "") : ;;
  *) echo "uso: $0 [juego|silencio]"; exit 1;;
esac
nvidia-smi --query-gpu=power.limit,power.draw,temperature.gpu,fan.speed,memory.used,memory.total \
           --format=csv
