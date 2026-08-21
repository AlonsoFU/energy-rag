#!/bin/bash
# Ajusta el limite de potencia segun la hora, para que la GPU no suene de noche.
#
#   09:00 -> 350 W   (1485 MHz, fan 100%)  el usuario esta despierto, que corra rapido
#   23:00 -> 160 W   ( 405 MHz, fan  43%)  silencioso para dormir
#
# Medido bajo carga real: 403 s/par a 160 W vs ~130 s/par a 350 W.
# El limite NO persiste tras reiniciar, asi que este cron tambien lo restablece.
H=$(date +%H)
if [ "$H" -ge 9 ] && [ "$H" -lt 23 ]; then W=350; else W=160; fi
ACTUAL=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits | cut -d. -f1)
[ "$ACTUAL" = "$W" ] || sudo -n nvidia-smi -pl "$W" > /dev/null 2>&1
