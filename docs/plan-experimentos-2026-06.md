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

## RESULTADOS

### Fase 2 — BGE `max_length` (HECHO, 2026-06): lever NULO + frente nuevo
Retrieval-only gold∈pool, BGE rr30, dev + extremo:
| | dev @5 | extremo @5 | ext_hundida @5 |
|---|---|---|---|
| ml=512 | 33/44 | 11/18 | 6/6 |
| ml=1024 | 32/44 | 11/18 | 6/6 |
- **`max_length` no mueve nada** (512≈1024). `ext_hundida` ya 6/6 a 512: el retrieval es por
  CHUNK, cada def vive en su fragmento chico → el truncado no pierde respuestas. El "30% truncado"
  no se traduce en fallos. **Descartado.**
- **El set extremo destapó el frente REAL** (por categoría, @5): ext_hundida 6/6, sufijo 2/3,
  autoridad 2/3, pero **distractor 0/3 y multi-parte 0/2**. Cuando la query nombra un concepto
  DOMINANTE que no es el sujeto (ej. "coordinador" → pregunta por el panel), ese término secuestra
  el retrieval; BGE no lo arregla (el distractor matchea de verdad). Es **comprensión/descomposición
  de query**, no reranking.
- NOTA: el sweep es SimpleRetriever-only; el ComplexRetriever (multi_query/step_back) podría ayudar
  a multi-parte en el pipeline completo — verificar con generación antes de invertir en un lever nuevo.

### Frente actualizado (reemplaza "situacional" genérico)
**Distractor + multi-parte (queries compositivas)**: detectar el SUJETO vs el término-contexto, o
descomponer la query. Conecta con `find_subject_concept` (Paso 1/2 previo). Candidatos: usar la rama
compleja para estas; o un paso de descomposición. NO max_length, NO más reranking.

## Orden recomendado
Fase 1 (ya) → Fase 2 → [Fase 0: decisión PR] → Fase 3 → Fase 4.
Pausar y revisar resultado al final de cada fase antes de seguir.
