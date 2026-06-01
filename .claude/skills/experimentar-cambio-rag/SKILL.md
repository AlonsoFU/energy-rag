---
name: experimentar-cambio-rag
description: Use when about to change ANY part of the Energy-RAG retrieval/generation pipeline (reranker, chunking, BM25/dense/RRF, fusion weights, query expansion/HyDE, top_k/top_rerank/pool_depth, curated inject, graph_boost, generation params, prompts). Triggers when a change is proposed "because it sounds better" without a measured before/after on an independent set, or when adopting a result seen only on the development eval.
---

# Experimentar un cambio de arquitectura RAG (con evidencia)

**Principio**: ningún cambio de arquitectura entra sin evidencia. Se **investiga** el
estándar y los **límites duros** de la técnica, se **mide en dev + held-out** (para cazar
overfit), no debe **regresar el grounding**, entra **flag-gated**, y se **documenta** —
incluyendo lo que se DESCARTÓ.

Esto NO reemplaza los skills genéricos; los usa. Lo propio de este proyecto es: dos sets
(dev + held-out gold-de-la-ley), grounding como métrica legal, y los gotchas del stack.

## Procedimiento

1. **Leer el contexto del proyecto PRIMERO** — `docs/architecture-status.md` (§8 pipeline
   vigente + límites por componente), el último `docs/campaign-*.md`/`handoff-*.md`, y la
   memoria `project_energy_rag_state`. Saber qué ya se probó y descartó.
2. **Investigar el estándar y los límites** — qué hace la industria 2026 para ese componente
   y los **límites duros** de la técnica nueva (ventana de tokens, hardware, latencia). Usar
   WebSearch / context7 para docs actuales. Escribir la **hipótesis**: qué CLASE de fallo
   arregla (def directa / situacional / alias / autoridad / negativo-trampa).
3. **Diseñar el experimento** → **REQUIRED SUB-SKILL: superpowers:brainstorming** (un lever por
   experimento; nunca varios cambios juntos).
4. **Medir cheap-first** — retrieval-only (`scripts/campaign_sweep.py`, gold∈pool@5/10/20) ANTES
   de generación (`scripts/campaign_generation_eval.py`, cita_ok/grounding). Recursos: gating
   GPU/RAM ≥5 min libres (drivers `campaign_*driver*.sh`); no matar entrenamientos ajenos.
5. **Dos sets** — dev `queries_independent.jsonl` + held-out `queries_holdout.jsonl` (gold LEÍDO
   de la ley, nunca derivado del sistema). **Generaliza = sube en AMBOS. Sube solo en dev =
   overfit → DESCARTAR.**
6. **No-regresión** — `grounding_pass` no baja (alucinación = error crítico legal), rechazos de
   negativos no se rompen. Revisar **por categoría**, no solo el global.
7. **Aterrizar flag-gated** — flag en `src/core/config.py` default OFF + A/B por env var; nunca
   flipear un default de producción en silencio (latencia/comportamiento = decisión de producto).
8. **Documentar y cerrar** → **REQUIRED SUB-SKILL: superpowers:verification-before-completion**.
   Actualizar `architecture-status.md` + doc de campaña + memoria, registrando wins **y rechazos**
   (overfit/nulo valen tanto como los wins). Commit al cambiar comportamiento, no al final.

## Gotchas verificados del stack (no re-descubrir)

| Gotcha | Realidad |
|---|---|
| BGE cross-encoder `max_length=512` | trunca ~30% de chunks (>1800 chars); el modelo aguanta 8192 |
| BGE en GPU GTX 1080 (Pascal sm_61) | "no kernel image" → correr en CPU |
| Ollama + JSON-schema constrained decoding | deadlock en qwen3.5 → patrón híbrido (verify post-hoc) |
| `transformers` cuelga al cargar | golpea API de HF Hub → `HF_HUB_OFFLINE=1` antes de importar |
| Postgres `energy_rag_pg` caído | eval da 0% FALSO → `docker start` + SELECT de sanidad antes |
| waiter `pgrep -f "src eval"` | se auto-matchea → deadlock; esperar por PID/archivo, no pgrep |

## Red flags (estás por violar la disciplina)

- "Mejora en el set de desarrollo, lo adopto" → falta held-out (HyDE/graph_boost_all eran overfit).
- "El global sube" sin mirar grounding ni categorías.
- Cambiar 2+ cosas a la vez → no sabés cuál movió la aguja.
- Gold derivado del propio sistema/curación (mide consistencia, no correctitud → infla).
- Asumir límites de la técnica (tokens/hardware/latencia) sin verificarlos.
