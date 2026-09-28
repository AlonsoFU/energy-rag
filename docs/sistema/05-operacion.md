# 05 · Operación

Repo de trabajo: `/home/alonso/Documentos/Github/energy-rag-postgres-rag` (worktree, rama
`adopt-winners`). El worktree `energy-rag` (rama `main`) está desactualizado. Ver también
`docs/manual-operacion.md`.

## Usar el sistema
```bash
cd /home/alonso/Documentos/Github/energy-rag-postgres-rag
PYTHONPATH=. venv/bin/python scripts/preguntar.py --buscar "¿me pueden cortar la luz si debo mes y medio?"   # 13 s
PYTHONPATH=. venv/bin/python scripts/preguntar.py "¿me pueden cortar la luz si debo mes y medio?"            # ~79 s
PYTHONPATH=. venv/bin/python scripts/preguntar.py --obligaciones coordinador
PYTHONPATH=. venv/bin/python scripts/preguntar.py --plazos | --cambios | --procesos | --impacto ID | --bitacora
```
Requisitos: contenedor `energy_rag_pg` arriba (se levanta solo), `ollama serve`,
`HF_HUB_OFFLINE=1`, `HF_HOME=/home/alonso/datos/hf`. Todo modelo vive en `/home/alonso/datos`.

Los números del sistema, generados (no escritos a mano):
```bash
PYTHONPATH=. venv/bin/python -m scripts.estado             # corpus, config adoptada, recall@10, cita_ok
PYTHONPATH=. venv/bin/python -m scripts.estado --markdown  # las mismas tablas para pegar en estos docs
```

## Dónde está cada script (limpieza 2026-09-28)
| carpeta | qué hay | cuántos |
|---|---|---|
| `scripts/` | lo que usa algo vivo: cadena del monitor, ingesta, embeddings, `preguntar.py`, `exp_think_paired.py`, `red_golden.py`, `estado.py` | 40 |
| `scripts/experimentos/` | experimentos ya decididos; `docs/` los cita como evidencia | 87 |
| `scripts/archivo/` | herramientas de un solo uso ya cumplidas (descargas puntuales, curación de glosario, migraciones). Nada de acá lo llama producción ni el cron | 134 |

Criterio mecánico de «vivo»: aparece en `scripts/*.sh`, `scripts/plan_maestro.txt`,
`docs/sistema/`, `src/` o `preguntar.py`. Si hace falta una de archivo: `git mv` de vuelta.

## Correr experimentos largos: la cola
**Nunca desde la sesión de Claude**: el harness mata procesos hijos por presión de RAM (pasó 2
veces). Todo experimento largo va por la cola del sistema:

1. Agregar una línea `etiqueta|comando` al inicio de `scripts/plan_maestro.txt`, con el criterio en comentarios arriba.
2. `scripts/trabajar.sh` (cron cada 10 min) copia el plan a `scripts/cola.txt` y llama a `scripts/runner.sh`.
3. `runner.sh` corre la primera tarea que no esté en `logs/cola_hechas.txt`; salida en `logs/cola_<etiqueta>.log`, eventos en `logs/runner.log`.
4. Si falla, reintenta hasta `MAX_INTENTOS=3` (retoma donde quedó). **Ojo:** un `timeout` interno cuenta como falla y se reintenta; para cortar de verdad, agregar la etiqueta a `logs/cola_hechas.txt` y matar el proceso.

Otros crons: `watchdog.sh` (cada 15 min), `retomar.sh` (cada 3 h), `latido.sh` (cada hora),
`gpu_vigia.sh` (cada minuto), `monitor_run.sh` (lunes 06:00, ver 03). `logs/` nunca se commitea.

## GPU (RTX 3090) y memoria
- La 3090 se cayó del bus (Xid 79) 6 veces entre el 08 y el 13-09; **no es potencia** (2 caídas sin carga). Tope a 180 W por `gpu_guard.sh`; `gpu_vigia.sh` registra temperatura, W y MHz con trabajo corriendo. Diagnóstico: `journalctl -k -b -1` y todos los arranques, nunca `dmesg`.
- Desde el 13-09: 0 Xid, máx 73 °C a 180 W.
- **RAM (14 GB) es el cuello, no la VRAM.** El embedder 4B va en CPU (3.7 GB con `num_ctx` 4096; 9.8 GB con 32768).
- El LLM `qwen3:30b-a3b` a ctx 32768 ocupa 22 GB de VRAM: cualquier proceso torch que tome la GPU antes lo desborda a CPU (49 → 43 capas).
- Modelo denso 27B: no cabe (25 GB, 12 % en CPU, 5-25 min por respuesta).

## Git
- Commits locales en `adopt-winners`. `origin/adopt-winners` es una copia vieja de agosto (22 commits cuyo contenido ya está en la rama local); no forzar push sobre ella.
- Reglas: no commitear `logs/`, no tocar `queries_diverse.jsonl` / `_rem.jsonl` / `ft_pairs.jsonl`.
- Tests: `tests/pipelines tests/parsers tests/components` → 7 fallas preexistentes conocidas (usar como línea base: mismas fallas antes y después de un cambio).
