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
| 19 | **E0 · robustez de eval** | set primario `balanced_v2` 339q + McNemar pareado, gen resumible | metodo | los sets 39/44/18 NO detectan Δ≤2 (ruido binomial ±2 = 1σ) | ✅ **adoptado** (método) |
| 20 | **E0b · `also_gold`** | auditar golds: definiciones alternativas válidas rechazadas | cita_ok | **62% → 84%** (+22, TODO por limpieza de eval) | ✅ **WIN** (era el eval, no el sistema) |
| 21 | **glossary_inject** | arista determinista término-glosario→artículo padre, inyectado al top-k sin desplazar | cita_ok | **233→249 (+16, 0 pérdidas), McNemar p=0.0000** | ✅ **WIN mayor** (adoptado, default ON) |
| 22 | M1 pool 50→100 (pareado limpio) | re-test sobre eval limpio + glossary_inject ON | cita_ok | **252→252, 0 flips, p=1.0000.** 41 top-10 cambiaron, ninguno convirtió | ✗ **muerto definitivo** |
| 23 | RK1 · Qwen3-Reranker-4B | reemplazar BGE cross-encoder | recall@10 | BGE 237 vs Qwen3 239 = **Δ+2 ruido**, 17× más lento | ✗ el reranker no es el muro |
| 24 | **E3 · auditoría efecto escopeta** | ¿cita_ok infla por citar mucho? `hit` vs `hit_first` | cita_ok | **253 vs 243** → solo 11 (3.9%) por cita no-primera. **Métrica SANA**. Pero precisión media **0.43** | ✅ medición (descartó la sospecha) |
| 25 | **E0c · `unanswerable`** | 12 queries piden definiciones que el corpus NO contiene (auditados 2978 arts, 5 patrones) | cita_ok | **90.7% → 94.4%** (252/267). El sistema RECHAZA bien y el eval lo penalizaba | ✅ **WIN** (era el eval otra vez) |
| 26 | **D2 · leyenda de variable** | extractor para `TON : ...` / `Donde: DIP: ...` (sin marcador `a)` ni trigger de glosario) | cita_ok | 252→254 (+2), **p=0.6250 NO significativo**. Tabla 608→713 | ⚠️ **adoptado por CORRECCIÓN de datos**, no por el Δ |
| 27 | GEN8a · `think=True` | mover el razonamiento a canal separado (deja de contaminar la respuesta) | cita_ok | **254→237 (−17, 0 ganadas)**. Pero citas 13.2→2.6 y **precisión 0.42→0.64** | ✗ **negativo** (trade-off real) |
| 28 | GEN8b · prompt prefer-definition | ordenar citar el artículo que DEFINE, no el que sanciona/regula | cita_ok | 253→254 (+1), **p=1.0 FLAT**. citas 13.19→13.09 | ✗ el prompt no mueve el comportamiento |
| 29 | **GEN9a · parser de ordinales** | `CITATION_PATTERN` no aceptaba `[Art. primero de 1204012]`; 267/2978 arts (9%) no citables | cita_ok | **253→260 (+7, 0 pérdidas), p=0.016** | ✅ **WIN** (bug de producción) |
| 30 | GEN9b · prompt de ordinales | además, enseñar al modelo que los ordinales se citan | cita_ok | 260→261 (+1), **p=1.0 FLAT** | ✗ el parser ya bastaba |
| 31 | **GEN9c · quitar `<think>` del texto visible** | `think=False` NO suprime el razonamiento: el bloque queda DENTRO de `response` | cita_ok + precisión | **156/267 (58%) mostraban el monólogo al usuario**. Medido en corrida real: cita_ok 262→260 (**−2**), citas únicas 4.20→3.04, **precisión 0.42→0.58**, `<think>` visible 0/267 | ✅ **adoptado** (bug de producción) |
| 32 | GEN10 · `answer_doc_limit=5` | ¿menos docs → el modelo se compromete con el #1? | cita_ok | 262→261 (gana 1, pierde 2), **p=1.0 FLAT**. precisión 0.42→0.45 | ✗ flat |
| 33 | GEN11 · `answer_doc_limit=3` | idem, más agresivo | cita_ok | 260→261 (gana 3, pierde 2), **p=1.0 FLAT**. precisión 0.58→0.70, **tiempo 20.4→14.4 s (−30%)** | ✗ flat en calidad; ⏳ útil solo como palanca de LATENCIA |
| 34 | **NO-REGRESIÓN** (dev/coloquial/holdout) | los 6 cambios adoptados solo se habían medido en `balanced_v2` | cita_ok | coloquial **36/39** (hist 37/39) · dev **37/44** (hist 36/44) · holdout **17/18** (hist 17/18) → **±1, SIN REGRESIÓN** | ✅ verificado |
| 35 | GEN8a-v2 · `think=True` (comparación justa) | rehecho tras el fix de `<think>`: antes el brazo OFF contaba citas del bloque de razonamiento | cita_ok | **260→244 (gana 1, pierde 17), p=0.0001 SIGNIFICATIVO NEGATIVO**. precisión 0.58→0.66 | ✗ **confirmado negativo** (no era artefacto) |
| 36 | GEN12 · híbrido `think` | intento 0 con `think=True`; si RECHAZA o no deja cita válida → reintento con `think=False` | cita_ok + precisión | **260→250 (gana 1, pierde 11), p=0.0063 NEGATIVO**. `cita_limpia` +15, `cita_perfecta` +38 | ✗ recupera 6 de los 16 golds, no alcanza |
| 40 | GEN13 · marcar el artículo DEFINITORIO en el prompt | `glossary_inject` SABE cuál define; se marca `<<< ESTE ARTICULO DEFINE "X" >>>` en vez de pedirle al LLM que adivine el rol | cita_ok | **261→260 (gana 3, pierde 4), p=1.0 FLAT**; precisión 0.66→0.66 | ✗ **flat** — 3er intento fallido por el lado del prompt |
| 39 | GEN2b · self-consistency **N=5** vs N=3 | ¿más muestras = consenso más robusto? | cita_ok + precisión | **262→263 (p=1.0 FLAT)**; precisión **0.63→0.57**, citas únicas 2.65→3.08, tiempo 71→98 s | ✗ **descartado** — ver caveat |
| 38 | D3 · TRIGGER ampliado del extractor | el trigger exigía "se entenderá por"; perdía artículos que ENUMERAN definiciones ("los recursos que siguen: 1) Reposición: ...") | cita_ok | 260→261 (gana 3, pierde 2), **p=1.0 FLAT**. Tabla 713→**743**. Convirtió `Reposición` (el objetivo) | ⚠️ adoptado por CORRECCIÓN de datos, no por el Δ |
| 37 | **GEN2 · self-consistency N=3** | 3 generaciones a T=0.7; consenso = citas en ≥2; se elige la respuesta más respaldada | cita_ok + precisión | **cita_ok 260→259 (p=1.0 FLAT)** · **`cita_limpia` +18** · **`cita_perfecta` +29** · precisión 0.59→**0.66** · tiempo 20.8→**61.4 s** | ✅ **WIN de CALIDAD** — el único que sube precisión SIN costar aciertos |

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

---

## 6. Campaña 2026-08 — qué movió la aguja (y qué no)

Detalle completo: `campaign-def-recall-2026-08.md`. Backlog vivo: `backlog-mejoras.md`.

### Recorrido de la métrica
```
62%    eval sucio (rechazaba definiciones alternativas validas)
84%    E0b  also_gold                                    +22  <- ERA EL EVAL
89.2%  glossary_inject (inyeccion determinista)          +16  <- unica mejora de sistema
90.7%  fixes de generacion (num_ctx + num_predict)        +3  <- ERA INFRA
94.4%  E0c  unanswerable (12 queries imposibles)          +4  <- ERA EL EVAL
94.8%  D2 leyenda de variable                            +2   (p=0.63, por correccion)
97.4%  GEN9a parser de ordinales                         +7   <- ERA UN BUG DE CITAS
97.4%  GEN9c quitar <think> del texto visible        -2   <- corrige inflacion; precision 0.42->0.58
```
**Número final: 260/267 = 97.4%**, ahora con citas que el usuario REALMENTE VE.

⚠️ **Corrección de una estimación mía:** calculé offline que quitar el bloque `<think>` costaría
6 aciertos (260→254) recortando el texto y re-puntuando. Costó **2**. El cálculo no consideraba el
BUCLE DE REINTENTO: cuando la respuesta visible queda sin citas válidas, `verify_citations` falla,
el modelo regenera y produce una respuesta bien citada. **Re-puntuar texto viejo subestima el
efecto de un cambio que altera el bucle de generación** — hay que correrlo de verdad.
**De +35 puntos, ~29 vinieron de arreglar la MEDICIÓN o los DATOS y +7 de un BUG de citas.**
Un solo cambio de sistema (`glossary_inject`) convirtió. **Ningún cambio de MODELO convirtió nunca.**

### El caso GEN9a — por qué el bug se escondía
El parser rechazaba `[Art. primero de 1204012]`. Medido sobre las respuestas guardadas, el modelo
citaba ordinales **0 veces en 267** — parecía que simplemente no los usaba. La causa real es peor:
el modelo SÍ los emitía, `verify_citations` los daba por inválidos, el bucle de reintento le decía
*"tus citas eran inválidas"* y el modelo los evitaba en el siguiente intento. **El verificador roto
entrenaba al modelo a no citar ordinales dentro de la propia corrida**, y el texto final —lo único
que se guardaba— no dejaba rastro. Por eso re-puntuar los textos viejos daba +0 y solo una corrida
nueva reveló el +7.

### Bugs de infraestructura que se disfrazaban de resultados
Los 4 se encontraron persiguiendo cuelgues, no buscándolos. Cada uno falseaba mediciones:

| bug | efecto | cómo se veía |
|---|---|---|
| `num_ctx=16384` desbordado (prompt 15.6k + salida 2k) | cuelgue 900s; `gen()` devolvía `False` | queries "fallando" que eran timeouts |
| sin `num_predict` | ollama genera hasta llenar ctx; el fix de num_ctx lo destapó | timeouts nuevos tras "arreglar" lo anterior |
| `NOISE` regex: `Art\.`/`D\.O\.` + `\b` nunca matchea | líneas de enmienda DENTRO de definiciones, y palabras partidas | el trigger de TON no disparaba |
| `CITATION_PATTERN` sin ordinales | 267/2978 arts (9%) no citables; `strip_malformed_citations` los BORRABA | citas legales válidas desaparecían de la respuesta |
| resume con `c["q"]` vs `c["query"]` (except tragado) | regeneraba 279 queries desde cero, en silencio | "el experimento va lento" |
| `num_predict=2000` con `think=True` | el razonamiento consume el presupuesto → `response=""` | GEN8a daba 0/11: parecía negativo rotundo |

### Muros confirmados (no insistir sin hipótesis nueva)
- **Pool/profundidad de retrieval** — 0 flips en 279 pares (#22).
- **Reranker** — ningún cross-encoder rompe el sesgo funcional-vs-definitorio (#7, #23). Se sortea
  con **inyección determinista**, no con modelos mejores.
- **Prompt-engineering sobre el generador** — #28 flat, #29 marginal. Con `think=False` el modelo
  delibera y cita todo lo que mira; las instrucciones no lo frenan.

### Deuda de MEDICIÓN abierta (lo más importante que queda)
**`cita_ok` premia ROCIAR.** Medido en #27: con 4.04 citas únicas la precisión es 0.42 y acierta;
con 1.80 sube a 0.64 y falla. Mientras la métrica sea "¿alguna cita pega?", toda mejora de
*calidad* de cita se verá como regresión. Antes de más trabajo de generación hay que cerrar
**E1 (métrica con precisión / faithfulness)** — si no, se optimiza el número equivocado.

### Reglas que salieron a los golpes
1. **Auditar el gold ANTES de construir el fix** (evitó un extractor para 4 términos inexistentes).
2. **Auditar el eval exige las MISMAS normalizaciones que usa el eval** (`_normalize_art`, `º`/`°`,
   siglas con punto: `C.O.M.A.` vs `C.O.M.A`).
3. **Medir pareado, ambos brazos en la misma sesión** — comparar contra un baseline en disco mezcla
   el efecto con el flicker del LLM (fue lo que contaminó M2).
4. **Persistir el TEXTO de las respuestas**, no solo el booleano — sin eso no se puede auditar nada
   hacia atrás (se descubrió al intentar auditar #24 y hubo que regenerar todo).

### Scripts nuevos
```
exp_e0_baseline.py       baseline robusto resumible
audit_golds.py           E0b: also_gold
audit_unanswerable.py    E0c: detecta definiciones que el corpus no contiene
exp_glossary_inject.py   #21
exp_m1_paired.py         #22 (pareado, no contra baseline en disco)
exp_e3_shotgun.py        #24 (persiste texto + citas por query)
diag_refusals.py         separa fallas de RETRIEVAL vs de GEN
exp_d2_paired.py         #26 (swap de tablas para el brazo OFF)
exp_gen8_paired.py       #27
exp_genflag_paired.py    runner PAREADO reutilizable (FLAG/NAME) + cache de retrieval
```


---

## 7. No-regresión y caveats (2026-08-09)

### #34 — los 6 cambios NO rompen nada fuera de `balanced_v2`
```
coloquial        36/39 = 92.3%   historico 37/39 (94.9%)   -1  (flicker LLM)
dev_independent  37/44 = 84.1%   historico 36/44 (81.8%)   +1
holdout          17/18 = 94.4%   historico 17/18 (94.4%)    =
```
Importa porque `glossary_inject` y D2 se **diseñaron mirando fallas de balanced_v2** — eran los
candidatos naturales a overfit. No lo hay.

**⚠️ Error propio, repetido:** la primera lectura del script daba holdout 17/24 = 70.8% y parecía
regresión grave. Las 6 "fallas" extra eran queries de RECHAZO (`gold=None`: *"cómo hacer un queque
de zanahoria"*, *"capital de Australia"*) y el script exigía una cita para darlas por buenas.
**Es exactamente el error de E0c, que yo mismo documenté y volví a cometer**: un scorer que no
distingue "contestable" de "hay que rechazar". Regla reforzada: *todo scorer nuevo debe declarar
cómo puntúa el rechazo ANTES de correrlo.*

### CAVEAT de `glossary_inject`: queries ambiguas de una palabra
En dev y holdout hay 2 rechazos que el sistema ahora **responde**:
```
"qué es la comisión"      -> "La Comisión Nacional de Energía [Art. 5 de 1146553]"
"qué significa coordinado" -> definicion de "Coordinado"
```
Causa verificada: `def_exact` matchea ambos (`comisión`→1146553/5, `coordinado`→1160108/2), o sea
lo introdujo `glossary_inject`. **Los términos SÍ están definidos en el corpus**, así que la
respuesta es defendible; pero el set los marcaba como test de rechazo, porque son queries vagas
donde el usuario podría querer otra cosa ("comisión" también es una tarifa).

**Es un trade-off legal, no un bug:** ante un match exacto, el sistema ahora afirma en vez de
preguntar. Conecta directo con **D4 (UX de ambigüedad)**: cuando la query matchea varios conceptos
o es de una sola palabra, mostrar opciones / preguntar en vez de adivinar. Queda como el caveat
principal del mayor WIN de la campaña.

### Estado final de la campaña
- **cita_ok contestables: 260/267 = 97.4%** (`balanced_v2_clean`), citas visibles, precisión 0.58.
- **7 fallas duras**: Reposición · DIA · Ajustes · Infracciones graves · Tránsito ×3.
- Frentes AGOTADOS con las palancas disponibles: pool, reranker, think, prompts, recorte de docs.
- Siguiente valor real: **E1 (métrica con precisión)** y **D1 (vigencia/derogación)** — el único
  error *grave* que le queda al sistema es citar norma derogada.


---

## 8. E1 — métrica con precisión (2026-08-09) y la decisión que abre

`scripts/eval_metrics.py`. No reemplaza `cita_ok` (rompería la comparabilidad de toda la campaña):
la acompaña.

```
cita_ok      ¿alguna cita pega?                      (historica; PREMIA ROCIAR)
cita_first   ¿la PRIMERA cita pega?
precision    citas unicas correctas / citas unicas
cita_limpia  pega Y precision >= umbral              <- candidata a metrica de adopcion
rechazo_ok   en unanswerable/gold=None, rechazar ES el acierto
```

### Lo que revela sobre la config vigente
```
cita_ok      260/267 = 97.4%
cita_first   250/267 = 93.6%
cita_limpia  169/267 = 63.3%
BRECHA: 91 respuestas aciertan pero con MAS DE LA MITAD de sus citas erradas
```
Ej: `definición de Estado Deteriorado` acierta con **10 citas únicas y precisión 0.10**. El artículo
correcto llega enterrado entre nueve que no vienen al caso. Para uso legal eso no es un detalle.

### ⚠️ REVIERTE EL VEREDICTO DE GEN8a (#27/#35)
`think=True` fue descartado dos veces por `cita_ok` (−17 y −16, p=0.0001). Bajo métricas con
precisión **gana, y en todos los umbrales**:
```
                       cita_ok   cita_limpia(0.5)   precision   citas_uniq
think=False (vigente)   97.4%        63.3%            0.58         3.04
think=True              91.4%        69.3%            0.66         1.84

cita_limpia por umbral:  0.34   0.50   0.67   0.80   1.00
        think=False       174    169     94     90     84
        think=True        185    185    124    124    124
        delta            +11    +16    +30    +34    +40
```
Con el criterio más estricto (**todas** las citas correctas): 124 vs 84.

**No era un experimento negativo: era un trade-off que la métrica no sabía ver.** Es la
confirmación del diagnóstico de #24/#27: `cita_ok` premia rociar.

### DECISIÓN ABIERTA (de producto/legal, no técnica)
```
prioridad "nunca perder el articulo correcto"  -> think=False (config vigente). Pierde precision.
prioridad "no citar normas equivocadas"        -> think=True.  Pierde 16 golds.
```
16 queries donde el sistema deja de dar el artículo correcto, contra 40 respuestas más sin ninguna
cita errada. **No se adopta unilateralmente**: depende de si en el uso real es peor no encontrar la
norma o entregarla mezclada con normas que no aplican.
Camino intermedio no probado: `think=True` + reintento con `think=False` cuando la respuesta no
cita nada válido (recupera golds sin reintroducir el ruido).


---

## 9. GEN12 / GEN2 (2026-08-10) — cómo subir precisión sin perder aciertos

Las tres formas probadas de reducir el rociado de citas, ordenadas por lo que cuestan:

```
                       cita_ok        cita_limpia  cita_perfecta  precision  seg
config vigente         260/267            170           85          0.59     20.8
think=True (#35)       244  (-16, p=1e-4)  185          123          0.66     24.1
hibrido think (#36)    250  (-10, p=6e-3)  185          123          0.66     ~40
self-consistency (#37) 259  ( -1, p=1.0)   188          114          0.66     61.4
```

**GEN12 (híbrido) falló la hipótesis.** Se diseñó para recuperar los 16 golds que pierde
`think=True` reintentando con el modo actual cuando el 1er intento rechaza. Recuperó **6**; siguen
faltando 10 y la caída sigue siendo significativa (p=0.0063). Conclusión: los golds no se pierden
solo por RECHAZAR — también porque `think=True` se compromete con el artículo funcional en vez del
definitorio (el sesgo de #27), y eso el reintento no lo detecta.

**GEN2 self-consistency es el WIN.** Es el único que sube la precisión (0.59→0.66, +18 `cita_limpia`,
+29 `cita_perfecta`) **sin caída significativa de `cita_ok`** (−1, p=1.0). Coste: **3× el tiempo**
(20.8 → 61.4 s por respuesta). Es un intercambio de LATENCIA por CALIDAD, no de calidad por calidad.

⚠️ **Bug de la lectura automática, corregido:** `auto_report.py` etiquetaba como TRADE-OFF cualquier
`d_ok < 0`, sin mirar significancia — y marcó así a GEN2, que en realidad es adoptable. Ahora exige
`p < 0.05` para llamarlo trade-off. *Un heurístico que ignora la significancia esconde WINs limpios.*


---

## 10. GEN2b (N=5) — negativo, pero el resultado es sobre MI DISEÑO, no sobre N

```
                cita_ok        precision  citas_uniq  seg
N=3 (adoptado)  262/264          0.63       2.65      71.0
N=5             263/264 (p=1.0)  0.57       3.08      97.9
```

**No prueba que N=5 sea peor que N=3.** El umbral de consenso quedó FIJO en "≥2 apariciones"
en vez de escalar con N:
```
N=3 -> 2/3 = 67% de las pasadas   (exigente)
N=5 -> 2/5 = 40% de las pasadas   (laxo)  <- entra ruido
```
Con más muestras, más citas alcanzan un umbral que no se movió, así que **el filtro se afloja**
y la precisión baja. La comparación justa sería `≥ceil(N/2)` (3 de 5).

**Se descarta igual** porque N=3 ya entrega la ganancia y E6 está agotado: re-correr 3h para
recuperar 1-2 puntos en la etapa que ya funciona no tiene retorno. Queda anotado por si alguien
retoma self-consistency: **el umbral debe ser proporcional a N**.

**Con esto E6 (RESPONDER) queda CERRADO.**
```
cita_ok       262/264 = 99.2%
cita_limpia   ~188/264 = 71%
precision     0.63
latencia      71 s/respuesta (N=3)
```
Residuo: 2 fallas. Frentes agotados: pool · reranker · think · híbrido · 2 prompts · 2 recortes
de docs · self-consistency N=5.


---

## 11. GEN13 (marcar el definitorio) — flat, y por qué importa el cómo falló

```
cita_ok      261/264 -> 260/264   (gana 3, pierde 4)  p=1.0 FLAT
precision    0.66 -> 0.66    citas unicas 2.57 -> 2.49
```

**Diseño (corregido a mitad de camino por el usuario).** El primer intento pedía al LLM que
clasificara el rol de cada artículo (define / regula / sanciona). El usuario lo cuestionó y tenía
razón: **ese es justo el juicio que el modelo no sabe hacer** — las 2 fallas restantes existen
porque confunde "define" con "regula". Se descartó SIN correr; habría repetido GEN8b (flat).
La versión corrida usa el dato determinista que ya teníamos: `glossary_inject` sabe cuál artículo
define (match exacto en `fragmentos_definicion`) y esa información se tiraba al pasarlo al prompt
como un doc más. Ahora se marca en el encabezado.

**Lo revelador son las PÉRDIDAS**, no el total:
```
PIERDE  que significa DIA
PIERDE  definicion de Infracciones gravisimas
PIERDE  que significa Infracciones graves
```
Son términos cuyo gold está en **varias normas**. La marca apuntó a UNA definición y el modelo
dejó de citar la otra, que también era válida. **La marca es determinista pero elige mal cuando
hay ambigüedad** — arrastra el `ORDER BY length(texto) DESC LIMIT 1` de `def_exact`, que es un
criterio arbitrario.

**Conclusión: es el 3er intento fallido de arreglar esto por el lado de la PRESENTACIÓN**
(GEN8b prompt-prefer-definition · GEN13 roles vía LLM, descartado · GEN13 marca determinista).
Patrón: **si el dato subyacente es ambiguo, ninguna presentación lo salva.**
→ El fix real es **G4 (entity resolution)**: desambiguar los 42 términos definidos en >1 norma
por contexto/jerarquía en vez de por longitud de texto.
