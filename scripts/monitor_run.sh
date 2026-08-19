#!/bin/bash
# B4.3 -- una pasada completa del monitor normativo. Para cron.
#
#   1. re-scrape de BCN (throttled, resumible)   <- unico paso que toca la red
#   2. diff contra el snapshot                    -> escribe norma_evento
#   3. informe de lo pendiente                    -> docs/monitor-ultimo-informe.md
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

  echo "--- 1. re-scrape BCN"
  timeout 7200 $E venv/bin/python -m scripts.rescrape_partial || echo "   (scrape incompleto, sigo)"

  echo "--- 2. diff"
  $E venv/bin/python -m scripts.monitor_diff

  echo "--- 3. informe"
  $E venv/bin/python -m scripts.monitor_report --marcar

  echo "--- 4. nuevo snapshot"
  $E venv/bin/python -m scripts.monitor_diff --snapshot

  echo "=== fin $(date '+%F %T') ==="
} >> "$LOG" 2>&1
