#!/bin/bash
# Watchdog de la cola de experimentos. Para cron cada 15 min.
#
# Motivo: el PC ya se colgo dos veces a mitad de corrida (freeze duro, sin Xid ni OOM en el
# kernel log). Los runners son resumibles y guardan tras CADA par, asi que relanzar es seguro
# y barato: retoma donde quedo.
#
# Recorre la cola en orden. Para cada etapa mira si ya esta completa; si no lo esta y NO hay
# nada corriendo, la relanza. Una sola etapa a la vez -- nunca dos procesos peleando la GPU.
#
# Instalar:
#   crontab -l 2>/dev/null | { cat; echo "*/15 * * * * /home/alonso/Documentos/Github/energy-rag-postgres-rag/scripts/watchdog.sh"; } | crontab -
# Desinstalar:  crontab -e   y borrar la linea
# Pausar:       touch /home/alonso/Documentos/Github/energy-rag-postgres-rag/.watchdog_off
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
LOG=logs/watchdog.log
[ -f .watchdog_off ] && exit 0

# ya hay un experimento corriendo -> no tocar nada
if pgrep -f "scripts.exp_(lookup_paired|veto_offtopic|ambiguedad|r5_fallback|adyacencia)" > /dev/null; then exit 0; fi

E="env -i HOME=/home/alonso PATH=/usr/local/bin:/usr/bin:/bin
   HF_HOME=/home/alonso/datos/hf HF_HUB_CACHE=/home/alonso/datos/hf/hub
   TRANSFORMERS_CACHE=/home/alonso/datos/hf/hub HF_HUB_OFFLINE=1
   BGE_DEVICE=cuda PYTHONPATH=."

# completo <dir_resultados> <n_esperado> -> 0 si ya termino
completo() {
  [ -f "data/eval/results/$1/result.json" ] || return 1
  n=$(./venv/bin/python -c "
import json,sys
try:
    d=json.load(open('data/eval/results/$1/result.json'))['detail']
    print(sum(1 for q in d if q.get('on') and q.get('off')))
except Exception: print(0)" 2>/dev/null)
  [ "${n:-0}" -ge "$2" ]
}

lanzar() {  # lanzar <nombre> <set> <log>
  echo "$(date '+%F %T') relanzo $1" >> "$LOG"
  docker start energy_rag_pg > /dev/null 2>&1
  sleep 5
  setsid $E SET="$2" NAME="$1" \
    ./venv/bin/python -m scripts.exp_lookup_paired >> "logs/$3" 2>&1 < /dev/null &
  exit 0
}

lanzar_veto() {  # igual que lanzar() pero con el runner del veto off-topic
  echo "$(date '+%F %T') relanzo $1" >> "$LOG"
  docker start energy_rag_pg > /dev/null 2>&1
  sleep 5
  setsid $E SET="$2" NAME="$1" \
    ./venv/bin/python -m scripts.exp_veto_offtopic >> "logs/$3" 2>&1 < /dev/null &
  exit 0
}

lanzar_amb() {  # runner de D4 (ambiguedad)
  echo "$(date '+%F %T') relanzo $1" >> "$LOG"
  docker start energy_rag_pg > /dev/null 2>&1
  sleep 5
  setsid $E SET="$2" NAME="$1" \
    ./venv/bin/python -m scripts.exp_ambiguedad >> "logs/$3" 2>&1 < /dev/null &
  exit 0
}

lanzar_r5() {   # R5: aporta algo el regex de fallback?
  echo "$(date '+%F %T') relanzo $1" >> "$LOG"
  docker start energy_rag_pg > /dev/null 2>&1
  sleep 5
  setsid $E SET="$2" NAME="$1" \
    ./venv/bin/python -m scripts.exp_r5_fallback >> "logs/$3" 2>&1 < /dev/null &
  exit 0
}

# ---- la cola, en orden ----
completo gate_fraseos 64       || lanzar gate_fraseos       data/eval/queries_fraseos_v1.jsonl    gate_fraseos.log
completo gate_noregresion 114  || lanzar gate_noregresion   data/eval/queries_operativas_v1.jsonl gate_noregresion.log
completo post_reingesta 64     || lanzar post_reingesta     data/eval/queries_fraseos_v1.jsonl    post_reingesta.log
completo post_reingesta_op 114 || lanzar post_reingesta_op  data/eval/queries_operativas_v1.jsonl post_reingesta_op.log
completo veto_fraseos 64       || lanzar_veto veto_fraseos   data/eval/queries_fraseos_v1.jsonl    veto_fraseos.log
completo veto_operativas 114   || lanzar_veto veto_operativas data/eval/queries_operativas_v1.jsonl veto_operativas.log
completo ambiguedad 35         || lanzar_amb  ambiguedad      data/eval/queries_ambiguos_v1.jsonl   ambiguedad.log
completo r5_fallback 61        || lanzar_r5   r5_fallback     data/eval/queries_sin_diccionario_v1.jsonl r5_fallback.log

echo "$(date '+%F %T') cola COMPLETA, nada que hacer" >> "$LOG"
