---
name: experimentar-cambio-rag
description: Use when making ANY change to the RAG pipeline architecture (retrieval, reranker, chunking, fusion weights, query expansion, generation params, injection, graph boost). Enforces the discipline of researching the current standard + its limitations BEFORE the change, measuring cheap-first on TWO sets (dev + held-out gold-from-law) to catch overfit, checking no-regression on grounding, landing flag-gated, and documenting wins AND rejections. Energy-RAG / regulación eléctrica chilena, stack Postgres+pgvector+Qwen3+Ollama local.
---

# Experimentar un cambio de arquitectura RAG (con evidencia)

> **Regla de oro**: ningún cambio de arquitectura entra "porque suena bien". Cada
> cambio se **investiga** (qué hace el estándar, qué límites tiene la técnica y la
> actual), se **mide en dos sets** (dev + held-out independiente para cazar overfit),
> se verifica **no-regresión** (grounding), entra **flag-gated** (default OFF), y se
> **documenta** — incluyendo lo que se DESCARTÓ y por qué.

Esta disciplina nació de la campaña 2026-06-01: HyDE y graph_boost_all parecían ganar
en el set de desarrollo pero el **held-out** los reveló como overfit; BGE generalizó.
Sin el held-out se habrían adoptado por error.

## Cuándo se activa

Cualquier toque al pipeline: reranker, chunking/re-chunk, BM25/dense/RRF, pesos de
fusión, HyDE/multi-query/step-back, top_k/top_rerank/pool_depth, inject curado,
graph_boost, params de generación, prompts. NO para fixes de bug puntuales.

## Procedimiento (en orden, no saltarse pasos)

### 1. INVESTIGAR el estándar y los límites (antes de tocar código)
- ¿Qué hace la industria 2026 para este componente? (ver `docs/architecture-status.md`,
  y WebSearch / context7 para docs actuales de la técnica/modelo).
- **Límites duros de la técnica nueva**: ventana de tokens, compatibilidad de hardware,
  costo/latencia, supuestos. Ej. reales ya cazados:
  - `bge-reranker-v2-m3` aguanta 8192 tok pero estaba clavado en `max_length=512` →
    ~30% de los chunks (>1800 chars) se truncaban.
  - Cross-encoder NO corre en GPU GTX 1080 (Pascal sm_61, "no kernel image") → CPU.
  - Ollama deadlockea con JSON-schema constrained decoding en qwen3.5 → patrón híbrido.
  - `transformers` golpea la API de HF Hub en cada carga → `HF_HUB_OFFLINE=1`.
- Escribir la **hipótesis**: qué CLASE de fallo debería arreglar (def directa /
  situacional-paráfrasis / alias / autoridad / negativo-trampa) y por qué.
- Mirar las limitaciones del approach ACTUAL para ese componente (qué pierde hoy).

### 2. INSTRUMENTAR cheap-first
- Medir **retrieval-only** (`scripts/campaign_sweep.py`: gold∈pool@5/10/20) ANTES de
  gastar generación. Es 10× más barato y aísla el efecto en el retrieval.
- Solo si retrieval mejora sin regresión → medir **generación** (`campaign_generation_eval.py`:
  cita_ok / grounding / answered).
- Recursos: gating GPU/RAM ≥5 min libres antes de evals largos (drivers `campaign_*driver*.sh`).
  NO matar el entrenamiento de otros proyectos; esperar. NO usar `pgrep -f` que se auto-matchea.

### 3. MEDIR EN DOS SETS (lo que caza overfit)
- **dev** = `data/eval/queries_independent.jsonl` (44q, set de iteración).
- **held-out** = `data/eval/queries_holdout.jsonl` (set reservado, gold LEÍDO de la ley,
  NUNCA usado para ajustar). Si un set nuevo se gasta iterando, deja de ser held-out.
- **Generaliza** = sube en AMBOS. **Overfit** = sube en dev y queda igual/baja en held-out → DESCARTAR.
- Gold por **lectura de la ley** (que el término/respuesta esté en el artículo), NUNCA derivado
  de la propia curación/sistema (eso mide consistencia, no correctitud — infla).

### 4. NO-REGRESIÓN (legal-safe)
- `grounding_pass` no debe bajar (alucinación = error crítico en RAG legal).
- Rechazos de negativos/off-corpus no deben romperse.
- Revisar por categoría, no solo el global (un global plano puede esconder +X/−X).

### 5. ATERRIZAR flag-gated
- Cambio detrás de flag en `src/core/config.py`, **default OFF**, hasta medido.
- Factory/patrón que permita A/B por env var (ej. `get_reranker()` + `USE_BGE_RERANKER`).
- Nunca flipear un default de producción en silencio (latencia/comportamiento = decisión de producto).

### 6. DOCUMENTAR (wins Y rechazos)
- `docs/architecture-status.md`: marcar el componente, sus límites medidos, los números.
- Doc de campaña/handoff del día con la tabla dev vs held-out, retrieval y generación.
- Memoria `project_energy_rag_state` (lo más vigente arriba).
- **Registrar lo DESCARTADO y por qué** (overfit/nulo) — vale tanto como los wins; evita repetirlo.
- Commit por cambio (ADR + handoff se actualizan al cambiar comportamiento, no al final).

## Anti-patrones (no hacer)
- Adoptar mirando solo el set de desarrollo. → usar held-out.
- Subir un número global sin mirar categorías ni grounding.
- Cambiar varias cosas a la vez (no sabés cuál movió la aguja). → un lever por experimento.
- Gold derivado del propio sistema/curación. → leer la ley.
- Asumir límites de la técnica sin verificarlos (tokens, hardware, latencia). → investigar.
