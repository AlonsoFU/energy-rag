---
name: experimentar-cambio-rag
description: Use when about to change ANY part of the Energy-RAG retrieval/generation pipeline (reranker, chunking, BM25/dense/RRF, fusion, query expansion/HyDE, top_k/top_rerank/pool_depth, curated inject, graph_boost, generation params, prompts). Triggers when a change is proposed "because it sounds better" without a measured before/after on an independent set, or when adopting a result seen only on the development eval.
---

# Experimentar un cambio de arquitectura RAG (con evidencia)

> Bilingüe a propósito: descripción en inglés (para que el matcher la encuentre), cuerpo en
> español (idioma de trabajo del proyecto).

**Principio**: ningún cambio entra sin evidencia en **dos sets** (dev + held-out, para cazar
overfit), sin **no-regresión de grounding**, y sin entrar **flag-gated**.

**Fuente de verdad** (no duplicar acá): `docs/architecture-status.md` — §8 pipeline vigente y
límites por componente, §8b límites de hardware. Este skill referencia ese doc; si los scripts,
sets o gotchas cambian, se actualiza **ahí** y este skill sigue valiendo.

## Procedimiento

1. **Leer el contexto primero** — `docs/architecture-status.md` (§8/§8b), el último
   `docs/campaign-*.md`/`handoff-*.md`, y la memoria `project_energy_rag_state`. Saber qué ya se
   probó y descartó.
2. **Investigar estándar + límites duros** de la técnica (ventana de tokens, hardware, latencia);
   WebSearch / context7 para docs actuales. Escribir la **hipótesis**: qué CLASE de fallo arregla.
3. **Diseñar** → **REQUIRED SUB-SKILL: superpowers:brainstorming**. Un solo lever por experimento.
4. **Medir cheap-first**: retrieval-only (gold∈pool) antes de generación (cita_ok/grounding). Los
   scripts viven en `scripts/campaign_*` (ver §8 si cambiaron de nombre). Recursos: gating
   GPU/RAM ≥5 min libres; no matar entrenamientos ajenos; esperar por PID/archivo, no `pgrep -f`.
5. **Dos sets**: dev + held-out (gold LEÍDO de la ley, nunca derivado del sistema). **Generaliza =
   sube en AMBOS. Sube solo en dev = overfit → DESCARTAR.**
6. **No-regresión**: `grounding_pass` no baja (alucinación = error crítico legal); rechazos de
   negativos no se rompen. Revisar **por categoría**, no solo el global.
7. **Flag-gated**: flag en `src/core/config.py` default OFF + A/B por env var. Nunca flipear un
   default de producción en silencio (latencia/comportamiento = decisión de producto).
8. **Cerrar** → **REQUIRED SUB-SKILL: superpowers:verification-before-completion**. Documentar en
   `architecture-status.md` + doc de campaña + memoria, registrando wins **y rechazos**.

## Hardware: "más lento" ≠ "bloqueado"

- **Solo más lento** (corre en CPU, tarda más): NO es bloqueo → **medílo igual** (background). La
  lentitud es dato de **costo/latencia** (decisión de producto, mejora con mejor hardware), no
  razón para saltarse el experimento.
- **Bloqueo duro** (literalmente no ejecuta): registralo como mejora teórica futura en
  `architecture-status.md §8b` (hipótesis + límite exacto + qué lo desbloquea).
- Regla: "tarda más" ⇒ se mide; "no arranca" ⇒ se registra. "No medible hoy" ≠ "no sirve".

## Red flags (estás por violar la disciplina)

- Adoptar por mejora **solo en dev** → falta held-out (así se colaron HyDE y graph_boost_all = overfit).
- Mirar el **global** sin grounding ni categorías.
- **Descartar** un lever "porque corre lento en CPU" → eso es costo, no bloqueo: medilo.
- Cambiar **2+ cosas** a la vez.
- Gold derivado del **propio sistema/curación** (mide consistencia, no correctitud → infla).

## Mantenimiento

Lo volátil (pipeline, scripts, sets, gotchas, límites de hardware) vive en
`docs/architecture-status.md` §8/§8b — **única fuente de verdad**. Este skill solo codifica la
*disciplina* (estable) y apunta ahí. Al renombrar scripts/sets o agregar gotchas: actualizar
`architecture-status.md`; revisar este skill solo si cambia la disciplina, no los detalles.
