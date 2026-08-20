#!/bin/bash
# Cambia el limite de potencia de la GPU segun para que la vas a usar.
#
#   ./scripts/gpu_modo.sh juego      350 W  -- FPS completos, ventilador 100%
#   ./scripts/gpu_modo.sh noche      160 W  -- evals de noche, ventilador 43%
#   ./scripts/gpu_modo.sh silencio   120 W  -- casi el mismo ruido y la MITAD de clocks
#   ./scripts/gpu_modo.sh            muestra el estado actual
#
# Medido bajo carga real (eval con qwen3:30b-a3b):
#   350 W  1485 MHz  fan 100%   ~130 s/par
#   200 W   915 MHz  fan  75%
#   160 W   405 MHz  fan  43%   <- mejor relacion ruido/velocidad
#   120 W   210 MHz  fan  40%   <- NO vale: mismo ruido que 160 y la mitad de clocks
#
# OJO: el costo NO es lineal. Medi mal la primera vez ("20% mas lento") con pocas
# muestras; bajo carga sostenida 120 W hunde los clocks a 210 MHz de 2100 -> ~5x.
#
# El limite NO persiste tras reiniciar: al bootear vuelve solo a 350 W.
case "${1:-}" in
  juego|game|350)     sudo nvidia-smi -pl 350 > /dev/null && echo "GPU -> 350 W (juego)";;
  noche|160)          sudo nvidia-smi -pl 160 > /dev/null && echo "GPU -> 160 W (noche)";;
  silencio|quiet|120) sudo nvidia-smi -pl 120 > /dev/null && echo "GPU -> 120 W (silencio)";;
  "") : ;;
  *) echo "uso: $0 [juego|noche|silencio]"; exit 1;;
esac
nvidia-smi --query-gpu=power.limit,power.draw,temperature.gpu,fan.speed,memory.used,memory.total \
           --format=csv
