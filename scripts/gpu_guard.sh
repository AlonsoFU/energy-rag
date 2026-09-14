#!/bin/bash
# GUARDA DE GPU -- corre ANTES de lanzar cualquier trabajo que use la GPU.
# Sale 0 = sana, se puede lanzar. Sale != 0 = NO lanzar (motivo en logs/gpu_guard.log).
#
# Por que existe (2026-09-13): la 3090 se cayo del bus PCIe (Xid 79) SEIS veces:
#   05-08 18:38  07-08 21:18  11-08 10:18  14-08 20:56  08-09 12:51  13-09 22:02
# Dos SIN carga (11-08, 14-08) y una a 180 W (08-09): NO es potencia ni calor, es hardware
# (alimentacion o enlace). El sistema no tenia ninguna guarda: la cola se relanzaba sola a
# 350 W tras cada reinicio, y el 08-09 corrio horas con el modelo en CPU (VRAM 0 GB, CPU a
# 95 C) porque nadie verificaba que la GPU existiera.
#
# Bloqueo: `.gpu_bloqueo` en la raiz. SOLO lo borra una persona despues de revisar el
# hardware. Ningun script lo borra, retomar.sh tampoco.
set -u
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag || exit 1
mkdir -p logs
LOG=logs/gpu_guard.log
log(){ echo "$(date '+%F %T')  $*" >> "$LOG"; }
bloquear(){ { date '+%F %T'; echo "$*"; } > .gpu_bloqueo; log "BLOQUEO: $*"; }
XID='Xid .*: 79,|fallen off the bus'

# 0. bloqueo pendiente de revision humana
if [ -f .gpu_bloqueo ]; then log "NO LANZAR: .gpu_bloqueo presente -- $(tail -1 .gpu_bloqueo)"; exit 10; fi

# 1. ¿el arranque ANTERIOR termino con la GPU fuera del bus? Una vez por arranque.
#    OJO: se mira el journal del arranque -1. `dmesg` solo tiene el arranque actual, y por
#    mirar ahi se diagnostico mal dos veces ("sin errores de hardware", "cuelgue del driver").
BOOT=$(cat /proc/sys/kernel/random/boot_id)
if [ "$(cat logs/.gpu_guard_boot 2>/dev/null)" != "$BOOT" ]; then
  echo "$BOOT" > logs/.gpu_guard_boot
  CU=$(journalctl -k -b -1 --no-pager -o short-iso 2>/dev/null | grep -m1 -E "$XID" | cut -c1-19)
  if [ -n "$CU" ]; then
    bloquear "el arranque anterior termino con Xid 79 (GPU fuera del bus) a las $CU. Revisar cables PCIe y fuente."
    exit 11
  fi
fi

# 2. la GPU ya se cayo en ESTE arranque: no vuelve sin reiniciar
if journalctl -k -b 0 --no-pager 2>/dev/null | grep -qE "$XID"; then
  bloquear "Xid 79 en este arranque: la GPU no vuelve sin reiniciar"; exit 12
fi

# 3. nvidia-smi responde (si no, el trabajo cae a CPU y no avanza)
if ! Q=$(nvidia-smi --query-gpu=temperature.gpu,power.limit --format=csv,noheader,nounits 2>&1); then
  bloquear "nvidia-smi no responde: $Q"; exit 13
fi
T=$(echo "$Q" | cut -d, -f1 | tr -d ' ')
L=$(echo "$Q" | cut -d, -f2 | tr -d ' ' | cut -d. -f1)

# 4. no arrancar con la placa ya caliente
if [ "${T:-0}" -ge 80 ]; then log "NO LANZAR: GPU a ${T} C antes de empezar"; exit 14; fi

# 5. reaplicar el tope que eligio el usuario: se pierde en cada reinicio (vuelve a 350 W)
if [ -f .gpu_limite ]; then
  W=$(tr -dc 0-9 < .gpu_limite)
  if [ -n "$W" ] && [ "$L" != "$W" ]; then
    if sudo -n nvidia-smi -pl "$W" > /dev/null 2>&1; then log "tope reaplicado: $L W -> $W W"
    else log "NO LANZAR: no pude reaplicar el tope de $W W (esta en $L W)"; exit 15; fi
  fi
fi
log "OK  gpu=${T} C  tope=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader 2>/dev/null)"
exit 0
