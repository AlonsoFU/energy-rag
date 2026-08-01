# Registro de experimentos — Energy-RAG

Registro vivo de TODOS los experimentos (incluidos los fallidos). Sirve para no repetirlos
y para entender POR QUÉ los pocos que funcionaron, funcionaron.

Métrica que manda: **cita_ok** = ¿el sistema cita el artículo gold?
Sets: coloquial 39 (frente difícil, lenguaje ciudadano) · dev/independent 44 (formal, control) ·
holdout 18 · balanced_v2 339.

> **Regla de oro (aprendida a la mala):** el *screen* (gold∈top5) **MIENTE**. No predice cita_ok.
> Todo candidato se confirma end-to-end (cita_ok) o no cuenta.

---

## 1. Tabla completa

| # | experimento | qué probó | métrica | resultado | veredicto |
|---|---|---|---|---|---|
| 1 | Embedder bake-off | 13 modelos (0.6B→9B): qwen3-emb 0.6b/4b/8b, e5, gte, jina, snowflake, bge-m3, sfr-mistral-7b, sfr-2r, nv-embed, linq-mistral, kalm, mpnet, granite, arctic, bge-gemma2-9B(GGUF) | screen + e2e | 4b-1024 mejor neto. 8b screen +2 → **e2e −1**. sfr/linq mejor screen, no convierte. gemma2-9B peor | ✗ agotado |
| 2 | **Generador bake-off** | small → qwen3:30b-a3b, 32b | cita_ok | **+9** (80→89) | ✅ **WIN** |
| 3 | **Alias union** | reescribe coloquial→término legal, unión con query original | cita_ok | **+3** coloquial, 0 regresión | ✅ **WIN** (adoptado) |
| 4 | **Gate off-topic AND** | conjunción de señales para rechazar | cita_ok | **+4** (26→30) | ✅ **WIN** (adoptado) |
| 5 | Ensemble retrieval | multi-query 4 patas (original+alias+glosario+rewrite 9b), unión RRF | screen +8 | **e2e −3** | ✗ espejismo |
| 6 | Verify-cite | 2º pase LLM elige la cita | 6 gen-fails | **0/6** rescatados | ✗ descartado |
| 7 | Reranker bake-off | 10 modelos: bge-v2-m3/large/base, mxbai-large-v1, mmarco-miniLM-es, gte-modernbert, qwen3-rerank 0.6b/4b, jina-v2, bge-gemma2 | screen | baseline **bge-v2-m3 imbatible** (cx 32) | ✗ nada mejor |
| 8 | Fusión RRF grid | k ∈ {10,20,60,80} × peso BM25:Vec | screen | +6 (+2%). **k y peso NO interactúan** | ✗ marginal, no adoptado |
| 9 | Chunking sweep | 17 estrategias (whole/glossary/inciso/inciso_robust/maxsplit/slide/recursive × none/light/path) | screen | `inciso_robust+path`: cx +2, **dev +10** | ⚠️ → #10 |
| 10 | **Chunking e2e** | inciso (7141 chunks) vs asis (3907), pipeline real + gen 30b | cita_ok | cx **−4** / dev +2 / **NET −2** | ✗ **espejismo, descartado** |
| 11 | Quant q5/q6 | cuantización del generador | cita_ok | = q4 | ✗ nada |
| 12 | Pool depth / top_k | 50/100/200 · top_k 10/15 | screen | sin ganancia | ✗ nada |
| 13 | HyDE | párrafo legal hipotético → vector | cita_ok | overfit / negativo | ✗ |
| 14 | doc2query | preguntas sintéticas por doc → BM25 | cita_ok | negativo | ✗ |
| 15 | citation_repair | reparar cita post-hoc | cita_ok | negativo | ✗ |
| 16 | concept_inference | LLM infiere concepto legal → retrieval | retrieval +3 / **gen −1** | ✗ trade-off | ✗ |
| 17 | Fine-tune 0.6B | embedder con pares | screen | overfit | ✗ |
| 18 | LLM-rewrite (30b) | reformular query | — | se cuelga; con 9b entra al ensemble (#5) | ✗ |

**Diagnóstico auxiliar (no experimento, medición):** `exp_stage_split.py` →
coloquial gold∈pool@50 = **39/39** (el embedder NUNCA falla el pool); el reranker no lo sube a top5 en 11.
dev: 4 pool-miss (2× def enterrada art225, 2× entidad-por-función SEC/Panel) + 4 reranker-miss.

**QA de estructura** (`exp_chunk_qa.py`): 2442/2978 arts quedan en 1 chunk; 378 grandes 1-chunk;
29 arts con marcadores no cubiertos (§14, N°11, guion3, romano1).

---

## 2. Los que funcionaron — cuánto y POR QUÉ

### ✅ WIN 1 — Generador `qwen3:30b-a3b` (+9 cita_ok, 80→89)
**El más grande de toda la campaña.**

**Teoría:** el pool casi siempre YA contiene el gold. Con el pool fijo, la única variable que
queda es *la capacidad del modelo de reconocer cuál documento responde y citarlo*. Mapear
"tope de ganancia" → el artículo de AVI/tasa-de-descuento es **conocimiento experto**, no
coincidencia de palabras. Un modelo más grande trae más de ese conocimiento latente y sigue
mejor la disciplina de citación.

```
pool con gold  +  selector débil  → cita vecino      (falla)
pool con gold  +  selector fuerte → cita el gold     (acierta)
```
Por eso **mejorar el selector convierte**, mientras **agregar candidatos empeora**.

---

### ✅ WIN 2 — Alias union (+3 coloquial, 0 regresión)
**Teoría:** cierra la **brecha de vocabulario** coloquial→legal.
```
"cliente libre"  →  la ley dice "Usuario No Sometido a Regulación de Precios"
   BM25:     0 palabras en común        → falla
   embedder: brecha semántica           → falla
   alias:    reescribe al término legal → matchea fuerte
```

**Por qué SÍ convierte (y el ensemble NO), aunque ambos "agregan búsquedas":**
- El alias es **quirúrgico**: inyecta *el término correcto*, no 50 candidatos extra.
- La **unión con la query original** (best-rank) protege: si el alias es malo, el original salva.
- El ensemble agregaba 3 rankings completos → ~150 candidatos, la mayoría **distractores**.

```
alias    : +1 señal precisa      → precisión ↑ → cita_ok ↑
ensemble : +150 candidatos ruido → precisión ↓ → cita_ok ↓
```
**Costo:** curación a mano. No escala solo. (Por eso el frente largo es grafo/fine-tune.)

---

### ✅ WIN 3 — Gate off-topic modo AND (+4, 26→30)
**Teoría:** no toca retrieval ni generación — arregla un error de **enrutamiento/abstención**.

El gate decide si la pregunta es del dominio. En modo OR, una sola señal débil bastaba para
rechazar → tiraba preguntas **legítimas** a la basura (cita_ok = 0 automático).
Modo **AND** exige que *ambas* señales coincidan para rechazar → menos falsos rechazos →
más preguntas se responden → más cita_ok.

```
OR : señal_a ∨ señal_b → rechaza  (rechaza de más, pierde in-domain)
AND: señal_a ∧ señal_b → rechaza  (rechaza solo lo claro)
```
Ganancia gratis: no cambia el pipeline, solo deja de descartar buenas preguntas.

---

## 3. La teoría unificada (por qué fallan casi todos)

**El recall está saturado; la precisión es la restricción.**

Medido: en coloquial el gold entra al pool@50 en **39/39** (100%). O sea:

```
el gold YA ESTÁ en el pool  →  agregar más candidatos NO agrega el gold
                            →  solo agrega DISTRACTORES
                            →  el LLM tiene más chances de citar el vecino
```

Por eso:

| tipo de palanca | qué le hace al pool | efecto cita_ok |
|---|---|---|
| más candidatos (ensemble, chunks finos, embedder "mejor") | +recall (ya saturado), **+ruido** | **baja** ✗ |
| mejor SELECCIÓN del pool (generador) | mismo pool, mejor elección | **sube** ✅ |
| inyectar el gold ARRIBA con señal precisa y sin ruido (alias) | +precisión | **sube** ✅ |
| dejar de descartar preguntas buenas (gate) | no toca el pool | **sube** ✅ |

**Regla operativa:** *precisión > recall*. Toda propuesta futura debe responder:
**"¿esto agrega el gold, o solo agrega ruido alrededor de un gold que ya estaba?"**

---

## 4. Vivos (sin probar end-to-end)

| palanca | por qué podría funcionar (según la teoría) |
|---|---|
| **Grafo concept→artículo** | inyecta el gold por **arista** (señal fuerte, 1 doc), no por semántica ni por más chunks → **quirúrgico como el alias**, pero automático/escalable. Ataca los pool-miss por función (SEC art2, Panel art212). ← **siguiente** |
| BM25 weight / doc2query | barato, pero es palanca de recall → la teoría predice poco |
| Fine-tune (embedder o reranker) | enseña el mapeo concepto→artículo → sube **precisión**, no solo recall. El fix de raíz, caro |

---

## 5. Scripts

```
exp_emb_bakeoff.py     embedders (13)
exp_gen_bakeoff.py     generadores
exp_reranker_bakeoff.py rerankers (10)
exp_chunk_sweep.py     chunking screen (17)
exp_chunk_qa.py        QA/anomalías de estructura
exp_chunk_e2e.py       chunking end-to-end (tabla paralela fragmentos_inciso)
exp_ensemble_e2e.py    ensemble end-to-end
exp_stage_split.py     diagnóstico: fallo-embedder vs fallo-reranker
```
Resultados en `data/eval/results/<experimento>/result.json`.
