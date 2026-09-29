# docs/

| carpeta / archivo | qué es | quién lo escribe |
|---|---|---|
| [`sistema/`](sistema/README.md) | **la documentación vigente**, por tema (01..06 + diagrama). Empezar acá | a mano, con números de `scripts/estado.py` |
| [`bitacora/`](bitacora/) | historia: handoffs, campañas, planes, `plan-operacion.md` (criterio y resultado de cada experimento) | a mano, no se edita hacia atrás |
| `monitor-ultimo-informe.md` | qué cambió en BCN esta semana y qué artículos del corpus lo citan | `scripts/monitor_report.py` (lunes 06:00) |
| `frontera-candidatas.md` | normas citadas desde el dominio que el corpus no tiene | `scripts/resolver_citas_normas.py` (monitor) |
| `descubrimiento-pendiente.md` | candidatas a ingerir; entrada de `bajar_candidatas.py` | monitor + a mano |
| `normativa-usada-en-discrepancias.md` | normas que el sector cita ante el Panel de Expertos | a mano; lo lee `bajar_candidatas.py` |

Los cuatro `.md` sueltos se quedan en la raíz de `docs/` a propósito: los leen o escriben scripts del
monitor semanal con esa ruta literal.

Último handoff: [`bitacora/handoff-2026-09-28.md`](bitacora/handoff-2026-09-28.md).
