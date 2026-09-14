---
name: gpu-seguridad
description: Use BEFORE launching or relaunching any GPU work (evals, queues, Ollama runs, re-embedding), before changing the GPU power limit, before re-enabling cron jobs, and whenever diagnosing a reboot, a crash, "the GPU disappeared", nvidia-smi errors, or a user question like "is it safe / did the PC restart / why did it shut down". The RTX 3090 in this machine has a recurring hardware fault (Xid 79, fell off the PCIe bus six times). This skill is the protocol so the load never runs unguarded and crashes are never misdiagnosed again.
---

# GPU: seguridad y diagnóstico

## El hecho que manda

La RTX 3090 se cayó del bus PCIe (**Xid 79**, seguido de Xid 154 "Node Reboot Required")
**seis veces**:

| fecha | carga | tope |
|---|---|---|
| 2026-08-05 18:38 | generando | sin dato |
| 2026-08-07 21:18 | cargando modelo | sin dato |
| 2026-08-11 10:18 | **ninguna** | sin dato |
| 2026-08-14 20:56 | **ninguna** | sin dato |
| 2026-09-08 12:51 | cargando modelo | **180 W** |
| 2026-09-13 22:02 | generando | 230 W |

Cero errores PCIe/AER en los 30 minutos previos a cada una.

**Conclusión: no es potencia ni calor.** Dos caídas sin carga y una a 180 W lo descartan.
Es una falla de hardware en la alimentación o el enlace de la GPU. **Bajar el tope de watts
no la arregla** y no se debe presentar como solución.

## Reglas de diagnóstico (se violaron dos veces)

1. **Después de un reinicio, el error está en el arranque ANTERIOR.** Mirar
   `journalctl -k -b -1`, nunca `dmesg` ni el arranque actual.
   - Error cometido: "las caídas de agosto no tuvieron errores de hardware" → falso, las
     cuatro eran Xid 79.
   - Error cometido: "el 08-09 fue un cuelgue del driver por el cambio de kernel" → falso,
     era Xid 79.
2. **Revisar TODOS los arranques, no solo el último**, para ver si es recurrente:
   ```bash
   for b in $(journalctl --list-boots -q | awk '{print $1}'); do
     journalctl -k -b "$b" --no-pager -o short-iso | grep -E "Xid|fallen off the bus"
   done
   ```
   Ojo: `journalctl -k` sin `-b` implica el arranque ACTUAL.
3. Distinguir los tres finales posibles de un arranque:
   - **Xid 79** en el kernel log → la GPU se cayó.
   - Secuencia `systemd-shutdown` / `Reached target reboot` → apagado limpio.
   - La última línea es actividad normal y después nada → **corte de energía** (cable,
     o el usuario apagó).
4. **Nunca decir "es seguro" o "el riesgo es bajo" sin haber hecho el paso 2.** Un "sin
   errores" basado en el arranque equivocado ya le costó confianza al usuario.
5. **No afirmar vigilancia continua.** Solo se ve la máquina cuando el usuario escribe.
   Lo que vigila entre mensajes son los scripts de abajo, no el asistente.

## Los guardrails que existen

| pieza | qué hace |
|---|---|
| `scripts/gpu_guard.sh` | Corre ANTES de lanzar. Bloquea si el arranque anterior terminó con Xid 79, si hay Xid en el actual, si `nvidia-smi` no responde, o si la GPU ya está ≥ 80 °C. Reaplica el tope de `.gpu_limite`. |
| `scripts/gpu_vigia.sh` | Cron cada minuto. Corta la carga si aparece Xid 79, si `nvidia-smi` muere, si el modelo generador cae 100 % a CPU, o si la GPU pasa 88 °C tres muestras seguidas. |
| `.gpu_bloqueo` | Lo crean la guarda o el vigía. **Solo una persona lo borra**, después de revisar el hardware. Ningún script lo quita, `retomar.sh` tampoco. |
| `.gpu_limite` | El tope elegido. Lo escribe `scripts/gpu_modo.sh`. El driver lo pierde en cada reinicio. |

Cableado: `runner.sh` no lanza sin `gpu_guard.sh`; `runner.sh`, `watchdog.sh` y
`trabajar.sh` salen si hay `.gpu_bloqueo`; `retomar.sh` no borra la pausa si hay bloqueo.

## Lo que NO se hace

- No borrar `.gpu_bloqueo`. Si el usuario quiere seguir, que lo borre él.
- No reactivar los cron de relanzamiento (marcados `# PAUSA-XID79` en el crontab) sin que
  el usuario lo pida explícitamente. Respaldo: `logs/crontab_backup_20260913.txt`.
- No subir el tope de watts como "arreglo" de las caídas.
- No lanzar GPU a mano saltándose `gpu_guard.sh`.

## Qué recomendar (físico, no se arregla por software)

En orden de probabilidad para Xid 79 en una 3090:
1. **Cables de alimentación PCIe**: cada conector de la placa con su propio cable desde la
   fuente, no un solo cable con "cola de chancho". Revisar que estén firmes y sin marcas de
   calor.
2. **Fuente**: modelo, potencia y antigüedad. La 3090 tiene picos transitorios muy por
   encima de su consumo medio.
3. **Asiento de la placa** en la ranura PCIe.
4. **BIOS**: la placa madre (Gigabyte X870 GAMING WIFI6) está en F8 del 2025-07-16. Probar
   actualizar y, como prueba, forzar la ranura a PCIe Gen3.
5. La GPU misma, si todo lo anterior está bien.
