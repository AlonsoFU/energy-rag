#!/bin/bash
# B4.3 -- una pasada completa del monitor normativo. Para cron.
#
#   0. repara scrapes rotos (limit 4/pasada)      <- toca la red
#   1. re-scrape del corpus EN DOMINIO (70)       <- toca la red, ~40 min a 20 s de throttle
#   2. diff contra el snapshot                    -> escribe norma_evento
#   3. informe de lo pendiente                    -> docs/monitor-ultimo-informe.md
#   3b. APLICA los cambios al corpus (con guardas)
#   3c. reproceso: duplicados, derogaciones, proceso, citas
#   4. nuevo snapshot                             -> baseline para la proxima pasada
#
# El scrape va PRIMERO y con throttle porque BCN devuelve 429 por cuota. Si muere a medias,
# los pasos 2-4 igual corren sobre lo que alcanzo a bajar (por eso estan desacoplados).
#
# Instalar (correr los lunes 06:00):
#   crontab -l 2>/dev/null | { cat; echo "0 6 * * 1 /home/alonso/Documentos/Github/energy-rag-postgres-rag/scripts/monitor_run.sh"; } | crontab -
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
mkdir -p logs
LOG=logs/monitor_$(date +%Y%m%d).log
E="env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin
   HF_HOME=/home/alonso/datos/hf HF_HUB_OFFLINE=1 PYTHONPATH=."

{
  echo "=== monitor $(date '+%F %T') ==="
  docker start energy_rag_pg >/dev/null 2>&1
  sleep 5

  echo "--- 0. reparar scrapes rotos (los que quedaron en 'Loading...')"
  timeout 1200 $E venv/bin/python -m scripts.rescrape_partial --limit 4 \
    || echo "   (reparacion incompleta, sigo)"

  echo "--- 1. re-scrape del corpus en dominio"
  # BUG que esto arregla: aca se llamaba a `rescrape_partial`, que NO detecta cambios --
  # solo re-baja los JSON que quedaron con 'Loading...'. Con 0 parciales pendientes no bajaba
  # nada y el diff daba 0 cambios PARA SIEMPRE, informando "sin cambios" sin haber mirado.
  # El detector real es `rescrape_modificadas`, y va con --alcance dominio (70 normas):
  # con el alcance viejo miraba 16 y las otras 54 podian cambiar sin que nadie se enterara.
  timeout 7200 $E venv/bin/python -m scripts.rescrape_modificadas --alcance dominio --frescura 6 \
    || echo "   (scrape incompleto, sigo)"

  echo "--- 2. diff"
  $E venv/bin/python -m scripts.monitor_diff

  echo "--- 3. informe"
  $E venv/bin/python -m scripts.monitor_report --marcar

  echo "--- 3b. aplicar al corpus los cambios detectados"
  # Cierra el ciclo: hasta ahora el monitor informaba "la norma X cambio" y el corpus seguia
  # respondiendo con el texto viejo. Cada norma pasa por las guardas de actualizar_norma
  # (identidad, el texto no encoge >10%, el articulado tampoco); lo que no pasa queda
  # pendiente para mirar a mano y NO se marca aplicado.
  $E venv/bin/python -m scripts.aplicar_cambios --aplicar || echo "   (sin cambios que aplicar)"

  echo "--- 3c. reproceso de lo que cambio"
  for m in detectar_articulos_duplicados detectar_derogaciones estructura_articulado; do
    $E venv/bin/python -m scripts.$m --aplicar || echo "   ($m fallo, sigo)"
  done
  $E venv/bin/python -m scripts.resolver_citas_normas --escribir || echo "   (citas fallo, sigo)"

  echo "--- 4. nuevo snapshot"
  $E venv/bin/python -m scripts.monitor_diff --snapshot

  echo "=== fin $(date '+%F %T') ==="
} >> "$LOG" 2>&1
