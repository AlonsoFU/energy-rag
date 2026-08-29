#!/bin/bash
# Consume la cola ENTERA, una tarea tras otra, sin esperar al cron.
# `runner.sh` hace una sola por invocacion porque esta pensado para cron :30; eso da una
# tarea por hora, demasiado lento cuando hay cola cargada y nadie mirando.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
# Se recuenta la cola en CADA vuelta: si se agregan tareas mientras drena, el bucle las toma.
# Antes se fijaba PEND al arrancar y quedaba corto -- paso con 9 tareas fijadas y 10 en cola.
while :; do
  PEND=$(grep -v '^#' scripts/cola.txt | grep -c .)
  # unicas: si dos drenadores corren a la vez, la misma etiqueta se anota dos veces
  # y el contador supera al total, cortando la cola antes de tiempo (visto: "10/9").
  HECHAS=$(sort -u logs/cola_hechas.txt 2>/dev/null | grep -c . || echo 0)
  [ "$HECHAS" -ge "$PEND" ] && break
  ./scripts/runner.sh
done
echo "$(date '+%F %T')  drenaje terminado: $(wc -l < logs/cola_hechas.txt)/$PEND" >> logs/runner.log
