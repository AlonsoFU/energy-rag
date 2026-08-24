#!/bin/bash
# Resucitador -- cron cada 5 horas. Deja el sistema en condiciones de seguir trabajando
# pase lo que pase mientras nadie mira: el PC se colgo dos veces, Postgres se apaga solo y
# el limite de la GPU no sobrevive un reinicio.
#
# NO decide nada: solo restablece condiciones y deja que el watchdog (cada 15 min) haga la cola.
#
# Instalar:  crontab -l | { cat; echo "0 */5 * * * <ruta>/scripts/retomar.sh"; } | crontab -
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
LOG=logs/retomar.log
mkdir -p logs

{
  echo "=== retomar $(date '+%F %T') ==="

  # 1. la pausa manual no debe sobrevivir para siempre; si el usuario paro, ya paso el rato
  [ -f .watchdog_off ] && rm -f .watchdog_off && echo "  quitada la pausa del watchdog"

  # 2. Postgres se apaga solo (medido varias veces)
  docker start energy_rag_pg > /dev/null 2>&1 && echo "  postgres arriba"

  # 3. el limite de potencia NO persiste tras reiniciar: vuelve solo a 350 W y suena
  W=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits 2>/dev/null | cut -d. -f1)
  if [ "${W:-0}" != "180" ]; then
    sudo -n nvidia-smi -pl 180 > /dev/null 2>&1 && echo "  GPU restablecida a 180 W (estaba en ${W}W)"
  fi

  # 4. Ollama tiene que estar sirviendo
  curl -s --max-time 5 http://localhost:11434/api/tags > /dev/null 2>&1 \
    || echo "  AVISO: ollama no responde"

  # 5. estado de la cola, para que el log sirva de bitacora
  ./venv/bin/python - <<'PY' 2>/dev/null
import json, os
for n in ("selfcons_n1", "filtro_operativas"):
    p = f"data/eval/results/{n}/result.json"
    if os.path.exists(p):
        d = json.load(open(p))["detail"]
        print(f"  {n}: {sum(1 for q in d if q.get('on') and q.get('off'))} pares")
PY
  ./venv/bin/python -c "
from src.components.vectorstore import with_connection
with with_connection() as c, c.cursor() as cur:
    cur.execute('SELECT count(*) FROM obligacion'); print('  obligaciones:', cur.fetchone()[0])
" 2>/dev/null || echo "  (DB no responde)"

  echo "=== fin $(date '+%F %T') ==="
} >> "$LOG" 2>&1
