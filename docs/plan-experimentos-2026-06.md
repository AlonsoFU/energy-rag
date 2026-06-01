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
| ml=2048 | 32/44 | 11/18 | 6/6 |
- **`max_length` no mueve nada** (512≈1024). `ext_hundida` ya 6/6 a 512: el retrieval es por
  CHUNK, cada def vive en su fragmento chico → el truncado no pierde respuestas. El "30% truncado"
  no se traduce en fallos. **Descartado.**
- **El set extremo destapó el frente REAL** (por categoría, @5): ext_hundida 6/6, sufijo 2/3,
  autoridad 2/3, pero **distractor 0/3 y multi-parte 0/2**. Cuando la query nombra un concepto
  DOMINANTE que no es el sujeto (ej. "coordinador" → pregunta por el panel), ese término secuestra
  el retrieval; BGE no lo arregla (el distractor matchea de verdad). Es **comprensión/descomposición
  de query**, no reranking.
### Verificación: ¿la rama compleja cubre el frente? NO (HECHO, 2026-06)
AdaptiveRetriever completo (multi_query/step_back) + BGE sobre el extremo (`A_adaptive_bge_extremo`):
| categoría | Simple+BGE @5 | Adaptive+BGE @5 |
|---|---|---|
| ext_sufijo | 2/3 | **3/3** |
| ext_distractor | 0/3 | 0/3 (1 a @10) |
| ext_multiparte | 0/2 | 0/2 (1 a @10) |
| total | 11/18 | 12/18 |
- La rama compleja recuperó 1 sufijo, pero **distractor y multi-parte siguen 0 a @5**. El pipeline
  completo (con expansión de query Y BGE) **NO resuelve queries compositivas** → se necesita un
  **lever NUEVO**, no la maquinaria existente.

### Lever DESCOMPOSICIÓN de query — PROBADO, DESCARTADO (2026-06)
Prototipo retrieval-only (`scripts/diag_decompose.py`, LLM parte en sub-preguntas → unión de pools
→ BGE) sobre el extremo: TOTAL **12→10/18 (−2)**. No ayuda distractor (0/3) ni multi-parte (0/2),
y **regresa ext_hundida 6→4** (partir queries limpias mete ruido). El LLM además no descompone los
distractores (subs=1). Descartado.
**Hallazgo dentro del fallo:** varios gold de distractor/multi-parte salen `base_rk=None` — NO se
recuperan ni como candidatos (212, 92, 1146553/48). No es ranking: es **recall/cobertura** (el
artículo operativo no comparte vocabulario con la query) y/o **gold discutible** (ej. financiamiento
del panel quizá es 212-13, no 212). → diagnóstico por-query antes que otro lever ciego.

### Diagnóstico por-query de los 5 fallos distractor/multi-parte (2026-06): el "0/3" estaba INFLADO
Leyendo la ley, 2 de los golds que puse en el set extremo están MAL/discutibles:
- "qué organismo resuelve discrepancias" gold 258171/212 → **212 es el FINANCIAMIENTO del Panel**,
  no su función de resolver. Gold equivocado mío.
- "cliente que negocia libremente su precio" gold 258171/147 → **147 lista los REGULADOS**; el
  cliente libre es por contraste (≈149/def). Gold discutible.
- Reales (gold OK pero recall gap): 92 (decreto expansión) y 1146553/48 (VATT método) no se
  recuperan; 29819/2 (SEC) quedó en rank 6 (casi).

**Conclusión corregida**: el frente "distractor" estaba inflado por gold malo. Prioridad real:
1. **Fase 4 (AHORA primero): curar/verificar el gold del set extremo + permitir múltiples gold
   válidos por pregunta.** Medir con gold malo lleva a perseguir levers fantasma.
2. Recall genuino de artículos OPERATIVOS (92, 1146553/48): no comparten vocabulario con la query
   → candidato = aristas concepto→artículo-operativo (curación), NO otro reranking.
LEVERS YA DESCARTADOS para esto: max_length, multi_query/step_back (rama compleja), descomposición.

### Fase 4 — golds corregidos + re-medición (HECHO, 2026-06)
Corregido gold panel (212→**208**, verificado) + multi-gold cliente [147,149] + soporte `also_gold`
en el harness. Re-medido Adaptive+BGE en extremo: **distractor 0/3 → 1/3, total 12→13/18.**
Detalle del residuo (gold ya correcto): panel 208 **rank 2 ✓** (era puro gold malo); 92 (decreto
expansión) None y VATT 1146553/48 None = **recall gap real** (artículo operativo sin vocab compartido);
147 cliente rank 10 (distractor lo hunde); SEC 29819/2 rank 7 (near-miss). → el frente real son
**~2 recall-gaps de artículos operativos** (curación de aristas concepto→operativo) + **distractor
genuino** (147). NO un lever de reranking. Confirma: arreglar el medidor cambió el diagnóstico.

## Orden recomendado
Fase 1 (ya) → Fase 2 → [Fase 0: decisión PR] → Fase 3 → Fase 4.
Pausar y revisar resultado al final de cada fase antes de seguir.
