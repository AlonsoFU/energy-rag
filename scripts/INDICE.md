# Índice de `scripts/` — qué se usa en operación y qué es evidencia

236 archivos. **No se borró nada**: cada experimento es la evidencia de una decisión
registrada en `docs/experimentos-registro.md`, y borrarlo dejaría el registro sin respaldo.
Tampoco se movieron de carpeta: los runners se invocan como `scripts.<nombre>` desde el
watchdog, los crons y entre ellos — mover 236 archivos rompería esas rutas a cambio de nada.

Lo que faltaba era saber **cuáles de los 236 se usan de verdad**. Son estos 14.

## Operación diaria
```
preguntar.py                 la interfaz. Todo lo demás se llega desde acá
mapa_obligaciones.py         obligaciones por sujeto, plazos, procesos, impacto
```

## Corren solas (cron)
```
watchdog.sh                  cada 15 min  relanza la cola si algo muere
retomar.sh                   cada 3 h     quita pausas, levanta Postgres, GPU a 180 W
monitor_run.sh               lunes 06:00  re-scrape + diff + informe
```

## Monitor normativo
```
rescrape_modificadas.py      re-baja de BCN y compara (--alcance dominio)
rescrape_partial.py          repara los JSON que quedaron en 'Loading...'
monitor_diff.py              compara contra el snapshot, escribe norma_evento
monitor_report.py            informe -> docs/monitor-ultimo-informe.md
monitor_schema.py            tablas del monitor
```

## Ampliar el corpus
```
bajar_candidatas.py          descarga de BCN (valida identidad: el buscador miente)
ingerir_nuevas.py            parsea e ingesta
marcar_fuera_dominio.py      frontera de mercados (MARCA, no borra)
estructura_articulado.py     obligacion.proceso desde los títulos del articulado
```

## Todo lo demás
`exp_*.py` (~90) son experimentos con su resultado en `docs/experimentos-registro.md`.
El resto son utilidades de una sola vez (ingesta, reparación, diagnóstico). Antes de escribir
uno nuevo, conviene buscar: es probable que ya exista.
