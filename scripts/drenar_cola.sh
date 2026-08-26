#!/bin/bash
# Consume la cola ENTERA, una tarea tras otra, sin esperar al cron.
# `runner.sh` hace una sola por invocacion porque esta pensado para cron :30; eso da una
# tarea por hora, demasiado lento cuando hay cola cargada y nadie mirando.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
PEND=$(grep -v '^#' scripts/cola.txt | grep -c .)
for _ in $(seq 1 "$PEND"); do
  ./scripts/runner.sh
  HECHAS=$(wc -l < logs/cola_hechas.txt 2>/dev/null || echo 0)
  [ "$HECHAS" -ge "$PEND" ] && break
done
echo "$(date '+%F %T')  drenaje terminado: $(wc -l < logs/cola_hechas.txt)/$PEND" >> logs/runner.log
