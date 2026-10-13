# Brief T01 — Esquema de candidatas y de corridas

Contrato: [`contrato.md`](contrato.md) · Spec: `docs/specs/cambios_dia-h1-reconocer-lo-nuevo.md`
· Cubre H1-CA-11, 13, 40.

## Objetivo

Crear las dos tablas de la sección 4 del contrato con un DDL idempotente.

## Archivos

- Crear `scripts/descubrimiento_schema.py`
- Crear `tests/descubrimiento/test_esquema.py`

Ningún otro archivo.

## Qué hacer

1. `scripts/descubrimiento_schema.py` con una constante `DDL` y un `main()`, calcado de
   `scripts/monitor_schema.py` (`CREATE TABLE IF NOT EXISTS`, índices `IF NOT EXISTS`).
   Exponer también `crear_esquema(conn)` para que los tests y otras tareas lo llamen.
2. Columnas, tipos y valores permitidos exactamente como en el contrato. `estado` y
   `clase_dominio` con `CHECK`. `estado` default `pendiente`; `vias`, `afecta` y
   `organismos` default `'[]'::jsonb`; `detalle` default `'{}'::jsonb`.
3. Índice por `estado` en `norma_candidata` y por `inicio DESC` en `descubrimiento_corrida`.

## Tests

Con `@pytest.mark.integration` y el fixture `db_clean`. El fixture no conoce estas tablas:
cada test llama a `crear_esquema` y limpia las suyas.

- Ejecutar el DDL dos veces no falla.
- Insertar y leer una candidata con todos los campos de H1-CA-11.
- Un `estado` fuera de la lista es rechazado.
- Insertar el mismo `id_norma` dos veces falla por llave primaria.

## Terminado cuando

Los tests existen y el DDL es idempotente. **En esta máquina no hay Postgres ni Docker
activo**: es probable que los tests de integración no se puedan ejecutar. En ese caso,
verifica al menos que el módulo importa y que `pytest --collect-only` los recoge, y dilo
en el reporte como "no ejecutados".

Nota: `src.storage.connection` carga `Settings` al importarse y falla si faltan variables
de entorno (el worktree no tiene `.env`). Para la comprobación de import, exporta valores
ficticios de `POSTGRES_*`; no crees ni commitees un `.env`.

## Fuera de alcance

Migraciones de alembic, tocar `norma_evento` o `tests/conftest.py`, cualquier lógica de
negocio.

## Entorno

`PYTHONPATH=. /home/alonso/.claude/jobs/6224a57d/tmp/venv/bin/python -m pytest tests/descubrimiento -q`
