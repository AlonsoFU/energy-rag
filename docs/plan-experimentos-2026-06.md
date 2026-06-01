# Plan de experimentos — Energy-RAG (post-campaña 2026-06-01)

Rama `feat/definition-source-resolver`. Disciplina: skill `experimentar-cambio-rag`
(dev + held-out, no-regresión de grounding, flag-gated, documentar wins y rechazos).

**Estado base**: BGE reranker + top_k=10 VALIDADO (adoptable; pendiente decisión de latencia + PR).
Frente abierto = clase **situacional** y **chunks largos truncados** (BGE ve solo 512 tok).

## Fase 0 — Consolidar lo ganado (decisión de producto, no experimento)
- Decidir si se activa `use_bge_reranker` + `top_rerank_override=30` + top_k=10 por default
  (costo: latencia CPU ~+seg/query).
- **PR/merge** de la rama (mucho acumulado sin mergear).

## Fase 1 — B: set held-out EXTREMO (habilitador, sin GPU)  ← empezar acá
~20-25 preguntas nuevas, gold LEÍDO de la ley, para destapar más errores y poder medir A honesto.
Categorías adversariales:
- **Respuesta hundida en artículo largo** (def al final del art 225 / glosario) → mide truncado.
- **Distractor** (la query nombra un concepto pero pregunta por otro).
- **Multi-parte** (2-3 sub-preguntas encadenadas).
- **Conflicto de autoridad** (ley vs reglamento, mismo término).
- **Sufijo raro** (72-X, 212-X) descrito sin el número.
- **Negativo-trampa** (suena eléctrico, no está en el corpus).
- **Alias/sigla ambigua** (SEC, CNE, COMA en contexto raro).

## Fase 2 — A: BGE `max_length` 512 → 1024 → 2048
- **Hipótesis**: cubre el ~30% de chunks truncados → +recall en "hundida-en-artículo-largo".
- **Medir**: cheap-first gold∈pool en dev + extremo; si promete → generación. Background, gating
  (lento en CPU = costo, NO bloqueo → se mide igual).
- **Éxito**: sube en AMBOS sets sin bajar grounding. Si solo dev → overfit, descartar.

## Fase 3 — Chunking (gap #2)
- **Re-chunk glosario fino** (1 def = 1 fragmento, art 225) + **contextual chunks** (resumen del
  artículo por LLM antepuesto). Ataca directo "operativo/paráfrasis no matchea".
- Costo: re-ingesta lenta (~3.900 chunks). Medible, no bloqueo.

## Fase 4 — Mejorar el MEDIDOR (eval)
- Aceptar **múltiples artículos gold válidos** por pregunta → arregla el fallo "gold discutible"
  (hoy cuenta MISS aunque la respuesta sea razonable).

## Orden recomendado
Fase 1 (ya) → Fase 2 → [Fase 0: decisión PR] → Fase 3 → Fase 4.
Pausar y revisar resultado al final de cada fase antes de seguir.
