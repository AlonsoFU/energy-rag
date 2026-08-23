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

---

## #41 — B1.2 FRASEOS VARIADOS: el número honesto (2026-08-18) — **CONFIRMA LA CIRCULARIDAD**

Primer experimento que NO prueba una mejora: mide **cuánto del 98.9% es circularidad**.
Set: `data/eval/queries_fraseos_v1.jsonl` (64q, generado por `scripts/build_fraseos_set.py`).
Runner: `scripts/exp_fraseos_paired.py`. Resultados: `data/eval/results/fraseos_v1/`.

**Diseño.** Pareado POR TÉRMINO, ambos brazos en la misma sesión (regla #4):
control `"qué es <T>"` (fraseo que el regex cubre) vs fraseo natural sobre el MISMO término y
el MISMO gold. Retrieval completo en los dos brazos — la diferencia **es** el retrieval.
Solo términos con `ok_off=True` en gen13_roles ⇒ una falla es atribuible al FRASEO, no al
término ⇒ **el drop medido es COTA INFERIOR**.

Dos grupos, dos fallas distintas del mismo mecanismo:
- **A (40q)** el gate `_is_definition_query` NO dispara.
- **B (24q)** el gate SÍ dispara, pero `_definition_concept` devuelve **la query entera** en vez
  del término, porque `_DEF_PREFIX` solo hace match al INICIO. Hallazgo NUEVO: "dame la
  definición de X", "cuál es la definición de X", "según la ley, qué es X" pasan el gate y aun
  así `def_exact` no encuentra nada.

```
                     control        fraseo
cita_ok  TOTAL       61/64 (95.3%)  56/64 (87.5%)   gano 2, perdio 7   McNemar p=0.1797
cita_ok  grupo A     39/40 (97.5%)  37/40 (92.5%)   p=0.6250
cita_ok  grupo B     22/24 (91.7%)  19/24 (79.2%)   p=0.3750
inject disparo       53/64          0/64            <- COBERTURA CERO
precision            0.66           0.57
citas unicas         2.27           2.53            <- rocia mas
rechazos             1/64           4/64
```

**Los tres hallazgos, en orden de importancia:**

1. **`glossary_inject` tiene cobertura 0% fuera de las 3 plantillas.** 53/64 → 0/64. El mecanismo
   que aportó +16 (el mayor win de retrieval del proyecto) **no existe** para un usuario que
   escribe normal. Esto era la sospecha; ahora está medido.

2. **Pero el sistema NO se derrumba: −7.8 pts, p=0.18 (no significativo con n=64).** Apagar el
   mecanismo estrella cuesta 5 queries netas. El resto del retrieval (4B + alias + BGE) rescata
   casi todo. **Corrección a la narrativa previa:** el 98.9% era circular en el MECANISMO, no
   inflado en el RESULTADO. Cota inferior — sobre términos difíciles el golpe sería mayor.

3. **El costo real está en la PRECISIÓN, no en el acierto.** 0.66 → 0.57 y 2.27 → 2.53 citas
   únicas: sin la inyección el modelo **rocía más para pegarle igual**. Consistente con que
   `cita_ok` premia rociar; la métrica de adopción (`cita_limpia`) casi no se mueve porque el
   acierto extra viene con basura.

**Modo de falla nuevo: el fraseo induce RECHAZOS.** 4 de las 7 pérdidas son `refuso=True`
(1/64 → 4/64). El sistema contesta "no sé" a una pregunta que con otro fraseo contesta bien:
```
[A] Tasas de falla de instalaciones de transmisión definición   refuso, 0 citas
[A] qué entiende la ley por Estado Deteriorado                  refuso, 0 citas
[B] necesito saber qué es TON                                   refuso, 0 citas
[B] según la ley, qué es Solicitante                            refuso, 10 citas (!)
```
Peor que fallar: el usuario recibe un no-hay-datos falso. Habrá que re-calibrar el gate off-topic
contra este set.

**NO parchear el regex.** El fix de B es una línea (permitir preámbulo antes del prefijo) y
recupera 24/64 casos, pero sería más regex como mecanismo principal — prohibido (CLAUDE.md
2026-08-17). **Este set es ahora el banco de pruebas de B2 (clasificador por embeddings):**
la meta es `inject 0/64 → ~64/64` sin tocar el regex.

**El número honesto del sistema:** `cita_ok` **87.5%** con fraseos naturales sobre términos
fáciles, no 98.9%. Y el 98.9% sigue siendo válido **solo** para las 3 plantillas del set primario.

---

## #42 — B2 PROBE: los embeddings agrupan por TEMA, no por INTENCIÓN (2026-08-18)

Antes de construir el clasificador del BLOQUE 2, medir su premisa. Barato (solo embeddings,
sin LLM): `scripts/exp_intent_probe.py`, ejemplos en `data/intents/ejemplos_v1.jsonl`
(83 ejemplos escritos a mano, 6 intenciones, **tópicos variados dentro de cada intención**
a propósito, para que la señal compartida sea la intención y no el tema).

```
1. LOO centroide   65/83 = 78.3%
1. LOO 1-NN        24/83 = 28.9%     <- azar = 16.7%
2. tema vs intencion: la INTENCION gana 1/6
     "cómo se calcula el peaje"  ->  tema 0.8299  vs  intencion 0.5892
     "qué es el costo marginal"  ->  tema 0.9147  vs  intencion 0.4437
3. queries_fraseos_v1: recall 'definicion' 50/64 = 78.1%, margen 1o-2o = 0.0658
```

**El coseno del embedder generalista está dominado por el TÓPICO.** "cómo se calcula el peaje"
se parece más a "qué artículo regula el peaje" (0.83) que a "cómo se determina el precio de
nudo" (0.59). El 1-NN casi al azar lo confirma: el vecino más cercano de un ejemplo es el que
habla del mismo tema, sin importar la intención. El centroide sobrevive (78%) porque promedia
tópicos, pero el margen 1º-2º de 0.066 hace cualquier umbral frágil.

**Conclusión que reordena el BLOQUE 2:** el problema real **no era clasificar la intención**,
era **extraer el término**. Y el término no hace falta inferirlo — está en la DB.

### #42b — `glossary_lookup`: extracción por DICCIONARIO (el fix real)

En vez de preguntar *"¿cómo está fraseada la query?"* (regex de prefijo), preguntar
*"¿qué término del glosario aparece en la query?"*. `fragmentos_definicion.termino` tiene 616
términos; match por **palabras completas** (sin esto "AR" matchea dentro de "solares"), gana el
**n-grama más largo**. `src/pipelines/glossary_lookup.py`, flag `glossary_lookup` (default OFF).

```
disparo de inject sobre queries_fraseos_v1 (64 fraseos naturales):
  regex de prefijo ....  0/64
  diccionario .......... 54/64      (control con fraseo cubierto: 53/64)

no-regresion sobre el set primario (279 in_domain), comparando el ARTICULO inyectado:
  mismo articulo ....... 267
  solo lookup inyecta ..  12        <- GANANCIA GRATIS
  solo regex inyecta ...   0        <- riesgo de regresion CERO
  inyectan distinto ....   0
```

Las 12 que solo el diccionario resuelve son **siglas con puntos** (`C.O.M.A.`, `V.A.T.T.`,
`A.V.I.`, `P.N.C.P.`): `_DEF_PREFIX` deja el punto final fuera del concepto (`C.O.M.A`) y
`def_exact` hace match exacto ⇒ no encuentra nada. Bug latente desde siempre, invisible porque
el eval nunca preguntó de otra forma.

El regex queda como **fallback** cuando el diccionario no encuentra término — el único rol que
le corresponde (CLAUDE.md 2026-08-17).

⚠️ **Riesgo abierto, aún NO medido:** una query de REGULACIÓN que contenga un término del
glosario ("qué artículo regula el Sistema de Transmisión Nacional") ahora dispara la inyección
de la DEFINICIÓN. El diccionario extrae, pero no decide *si corresponde inyectar*. **Ahí sí hace
falta el clasificador de intención, pero como GATE, no como extractor.** Medir sobre el set
operativo antes de adoptar.

**ESCALA:** costo por query O(tokens²) lookups en dict — constante respecto al tamaño del
glosario. Memoria ~5 MB por 100k términos. Lo que empeora al escalar es la **ambigüedad**: más
términos ⇒ más colisiones ⇒ pesa más el desempate arbitrario de `def_exact`
(`ORDER BY length(texto) DESC`). Ese es el frente G4.

---

## #43 — `glossary_lookup` e2e + GATE de intención (2026-08-18/19) — **el bloque 2, resuelto**

### #43a — e2e del diccionario, sin gate (`lookup_fraseos`)

Pareado sobre `queries_fraseos_v1`, misma query en ambos brazos, misma sesión.
OFF = concepto por regex de prefijo · ON = concepto por diccionario del glosario.

```
cita_ok       OFF 56/64  ->  ON 60/64   [gano 4, perdio 0]  McNemar p=0.1250
cita_limpia   OFF 45/64  ->  ON 42/64
inject        OFF  0/64  ->  ON 54/64
rechazos      OFF  4/64  ->  ON  2/64
precision     OFF  0.62  ->  ON  0.67
citas unicas  OFF  2.08  ->  ON  2.20
```

**Gana 4, pierde 0.** p=0.1250 porque McNemar no puede bajar de ahí con 4-0 (harían falta 5-0),
pero todo apunta igual: mecanismo recuperado, precisión arriba, rechazos a la mitad, cero
pérdidas. Cierra casi toda la brecha de fraseo: control 61/64 · sin lookup 56/64 · **con lookup
60/64**.

⚠️ **`cita_limpia` baja 3** y no es contradictorio con la precisión media: 7 queries GANAN
limpieza (4 pasan de fallar a acertar con precisión 1.00) y 9 la PIERDEN — siguen acertando pero
rocían más (`uniq 1→3`, `1→5`). Al inyectar entra un doc extra al pool y el modelo lo cita
*además* de los otros. Parte puede ser flicker de T=0.7 con `self_consistency_n=3`; no se puede
separar sin repetir la corrida.

### #43b — el riesgo medido: sin gate, el diccionario contamina lo operativo

```
inyecciones     fraseos_v1(+)  complex_v3(-)  holdout op.(-)
diccionario solo    54/64          20/51          7/19
```
"Cliente", "Ley", "Comisión", "Coordinador", "Aviso" son términos de glosario que aparecen en
**cualquier** pregunta. El diccionario extrae bien, pero **no decide si corresponde inyectar**.

Filtro por longitud del término — descartado, trade-off malo:
```
min 1 palabra   54/64   20/51      min 2 palabras   38/64   7/51
```

### #43c — el gate: clasificador, no coseno

`src/pipelines/intent_gate.py` + `scripts/train_intent_gate.py`. Regresión logística binaria
sobre el embedding de la query (mismo `qwen3-embedding:4b` MRL-1024 del retrieval); los
coeficientes van a `data/intents/gate_definicion_v1.json` y la inferencia en producción es un
producto punto — sin sklearn ni pickle en runtime.

```
gate definicion/no-definicion       recall   precision    F1
  regex `_is_definition_query`       0.864     0.997     0.925
  centroide (coseno)                 0.983     0.981     0.982
  logreg (5-fold CV)                 0.992     0.989     0.990
```
El coseno agrupa por tópico (#42) pero **la regresión logística sí separa**: aprende qué
dimensiones codifican la intención y descarta las del tema. Ese era el matiz que faltaba —
"los embeddings no sirven para intención" es falso; lo que no sirve es *el coseno crudo*.

**Composición del train, elegida midiendo 3 alternativas** (`fraseos_v1` SIEMPRE fuera):
```
A) solo 83 ejemplos a mano            inyecta 47/64   1/51   0/19
B) ejemplos + primario(279)           inyecta 52/64   0/51   0/19   <- elegida
C) ejemplos + primario + operativas    inyecta 51/64   0/51   0/19
```
⚠️ `queries_fraseos_v1` se excluye **deliberadamente** del entrenamiento: es el set de test.
Meterlo habría repetido exactamente el error que hizo circular al eval original.

**Resultado de la composición completa (fuera de muestra):**
```
inyecciones            fraseos_v1(+)  complex_v3(-)  holdout op.(-)
hoy (regex)                 0/64           0/51           0/19
diccionario solo           54/64          20/51           7/19
gate + diccionario         52/64           0/51           0/19
```
Cuesta **2 inyecciones correctas** y elimina **las 27 indebidas**.

Flags `glossary_lookup` + `intent_gate` (ambos default OFF). El regex queda de fallback cuando
el diccionario no encuentra término. Corriendo el e2e pareado de la composición completa.

**ESCALA:** gate = 1 embedding + producto punto de 1024 dims por query, constante respecto al
corpus. Hay que **reentrenar al cambiar de embedder** (los coeficientes son del espacio
vectorial) y al agregar intenciones. El diccionario es O(tokens²) lookups, también constante;
lo que empeora al escalar es la ambigüedad entre términos ⇒ frente G4.

---

## #44 — `glossary_lookup` + `intent_gate` **ADOPTADOS** (2026-08-19)

Cierra el BLOQUE 2. Dos corridas pareadas, ambos brazos en la misma sesión.

### Ganancia — `queries_fraseos_v1` (64 fraseos naturales, `gate_fraseos`)
```
cita_ok      OFF 56/64  ->  ON 62/64   [gano 6, perdio 0]  McNemar p=0.0312  SIGNIFICATIVO
cita_limpia  OFF 36/64  ->  ON 41/64
inject       OFF  0/64  ->  ON 52/64
rechazos     OFF  4/64  ->  ON  2/64
precision    OFF  0.53  ->  ON  0.61
```
El gate **mejora sobre el diccionario solo** (#43a): con gate gana 6 en vez de 4, y `cita_limpia`
SUBE (36→41) en vez de bajar (45→42). Evita inyecciones que ensuciaban la respuesta.

### No-regresión — `queries_operativas_v1` (114 queries, `gate_noregresion`)
```
cita_ok      OFF 98/114  ->  ON 99/114  [gano 4, perdio 3]  p=1.0000 FLAT
inject       OFF  3/114  ->  ON  3/114  <- IDENTICO
cita_limpia  OFF 68/114  ->  ON 62/114
precision    OFF  0.55   ->  ON  0.53
```
**El riesgo que estaba abierto queda cerrado:** el gate no dispara donde no debe. `inject`
idéntico en **114/114**, y las 3 que inyectaron son de definición legítima
(`qué es el sistema de transmisión nacional`, `qué es la comisión`, `qué significa coordinado`).
La predicción offline (0/51 en complex_v3, 0/19 en holdout) se cumplió.

### ⚠️ Hallazgo lateral, más importante que el experimento: LA VARIANZA DEL SISTEMA

```
queries donde cambio cita_ok:      7/114  — de esas, con inject IDENTICO: 7
queries donde cambio cita_limpia: 34/114  — con inject IDENTICO: 34
```
El retrieval fue **exactamente igual** en ambos brazos (inject 114/114 idéntico) y aun así
34 queries cambiaron `cita_limpia` y 7 `cita_ok`. Eso no es el flag: es **flicker de generación**
(T=0.7 + `self_consistency_n=3`).

**Piso de ruido medido del sistema, con el sistema IDÉNTICO:**
```
cita_ok      ~6%   (7/114)
cita_limpia  ~30%  (34/114)
```
Consecuencias para el método:
1. **`cita_limpia` no sirve como métrica de adopción sin pareado estricto.** Explica por qué
   saltaba errático entre corridas (en #43a bajaba 45→42, acá 68→62, en gate_fraseos SUBÍA 36→41).
2. Los baselines OFF de dos corridas del MISMO sistema difieren (`cita_limpia` 45 vs 36 sobre el
   mismo set) — **comparar contra un baseline en disco es inválido**, confirma la regla #4.
3. Cualquier Δ menor a ~7 en `cita_ok` sobre 114 queries es indistinguible de ruido.

### Decisión
**ADOPTADOS** `glossary_lookup=True` + `intent_gate=True` (default ON en `config.py`).
Ganancia significativa donde importa (fraseos naturales, p=0.0312, 0 pérdidas), sin regresión en
lo operativo. El regex queda de fallback cuando el diccionario no encuentra término.

---

## #45 — G4 entity resolution: **NO ES MEDIBLE con el eval actual** (2026-08-19)

Antes de construir G4 (desempate de los términos definidos en >1 norma, señalado 3 veces como
"el fix real"), medí offline si algún criterio de desempate le gana al actual
(`ORDER BY length(texto) DESC`). Sobre las 64 queries del eval cuyo término ES ambiguo:

```
longitud (HOY)     64/64 = 100%
jerarquia+fecha    64/64 = 100%
fecha mas nueva    64/64 = 100%
jerarquia+largo    64/64 = 100%
```

**Los 4 criterios empatan en 100%** porque `also_gold` marca TODAS las variantes como válidas.
El eval no puede distinguir entre elegir la definición del DECRETO 10 o la de la RESOLUCIÓN 711:
acepta ambas.

**Conclusión:** el riesgo legal de G4 es real en concepto (elegir la definición equivocada para
el contexto), pero **el eval actual es ciego a él**. Construirlo ahora sería trabajar sin
retroalimentación. Para atacarlo primero hay que decidir qué definición es la correcta para cada
contexto — y eso es una decisión de dominio (del usuario), no algo que yo pueda inferir del
corpus. Queda BLOQUEADO por falta de criterio, no por falta de implementación.

Dato útil que salió: de los **42** "términos ambiguos", solo **35 son términos reales**; 7 eran
fórmulas legislativas mal parseadas.

### Higiene del glosario (medido, NO adoptado)
`fragmentos_definicion` tiene **743 entradas, de las cuales 284 (38%) no son términos** sino
fórmulas de modificación ("Agrégase el siguiente inciso final", "Reemplázase el artículo 21…").
Contaminan `def_exact` y el diccionario de `glossary_lookup`.

PERO: no afectan ninguna query real —
```
glossary_lookup devuelve basura en:  fraseos 0/64 · operativas 0/114 · primario 0/279
```
Nadie pregunta "qué es Agrégase el siguiente inciso". Es **higiene para escala, no ganancia
medible hoy**: con más normas crecen las fórmulas y sube la chance de colisión. No se gastó GPU.

---

## #46 — El monitor cazó un gap del CORPUS, no un cambio normativo (2026-08-19)

Re-bajar las 25 normas modificadas (B3.3) destapó tres cosas, ninguna era la que se buscaba.

### 1. `content_hash` es inservible como detector de cambios
13 de 25 acusaron `texto_modificado`. Auditadas contra el contenido real: **todas cosméticas**.
```
LEY 20365   28.952 -> 28.952 chars   similitud 1.0000   0 bloques distintos
LEY 20410   71.100 -> 71.119 chars   similitud 0.9999   unica dif: ' Ley Historia de la'
```
`content_hash` es sha256 del texto CRUDO: cambia con cualquier espacio, `\xa0` o pedazo de
interfaz. → `src/pipelines/texto_hash.py` (normaliza antes de hashear). Falsos positivos
13 → 8, y de los 8 restantes varios siguen siendo ruido de UI (`jurisprudencia`, `autores`,
`historia de la ley`, `ley facil chile atiende`).

### 2. `normas.texto_completo` está truncado — pero NO afecta al RAG
```
                    texto_completo   suma de articulos
258171 DFL 4 (LGSE)      10.075          496.409     <- 330 articulos, completos
1058072 LEY 20720        18.910           18.392
```
Alarma inicial mía: "la LGSE tiene el 1.7% del texto". **Falso.** El RAG lee de `articulos`,
no de `normas.texto_completo`; la LGSE tiene sus 330 artículos íntegros. Solo 1 de 95 normas
tiene el campo realmente desfasado. Corregido antes de actuar sobre él.

### 3. Lo que SÍ es un gap real: normas sin artículos ingestados
```
normas totales             95
con 0 articulos            17
   de esas, ELECTRICAS     12   <- el sistema NUNCA puede citarlas
```
Entre ellas hay normas del dominio que importan:
```
1055073  LEY 20701   PROCEDIMIENTO PARA OTORGAR CONCESIONES ELECTRICAS
1059332  LEY 20726   MODIFICA LA LEY GENERAL DE SERVICIOS ELECTRICOS
1048990  DECRETO 1   FIJA PRECIOS DE NUDO PROMEDIO EN EL SIC
1122953  DECRETO 4   FIJA PEAJES DE DISTRIBUCION
1040103  LEY 20586   CERTIFICACION DE ARTEFACTOS PARA COMBUSTIBLES
```
Están en el catálogo pero sin articulado: el retrieval no las alcanza jamás. **Ningún
experimento de retrieval o generación podía arreglar esto** — es un agujero de ingesta, y
explica por qué ciertas consultas no tenían respuesta posible.

Además, 2 normas están MAL ETIQUETADAS (el `titulo` no corresponde al `tipo`/`numero`):
`237695 LEY 19940` cuyo título es "RESOLUCION 32 EXENTA NOMBRA REPRESENTANTE SUPLENTE" y
`252841 DECRETO 44` cuyo título es "RESOLUCION 838 OTORGA CONCESION DE ACUICULTURA".

### 4. Bugs propios corregidos en el camino
- La guarda anti-truncado rechazaba textos ÍNTEGROS que traen "Loading" en el footer
  (3 de 25 con el largo exacto igual). Ahora si el largo ≥ guardado se acepta.
- El crawler se degrada en tandas largas: DFL 1 baja 329.285 chars de a una y 25.401 dentro
  de una tanda. Se recicla el browser cada 5 normas (mitiga, no elimina: siguen 10 incompletas).

**Siguiente:** re-ingestar el articulado de las 12 eléctricas con 0 artículos. Es corpus, no
modelo — y por el historial del proyecto, eso es lo que convierte.

---

## #47 — `offtopic_glossary_veto` **DESCARTADO** (2026-08-20/21)

Origen: exp #44 midió 4 rechazos falsos en `queries_fraseos_v1` — el sistema contesta
"No encuentro esa información" a preguntas que con otro fraseo responde bien. Peor que fallar.

**Diagnóstico (correcto):** dos fallas que se suman en `is_off_topic`.
```
"necesito saber qué es TON"  ->  off_topic=True   oov=2/2   fuera=['necesito','saber']
```
1. El preámbulo conversacional (`necesito`, `saber`, `quisiera`) no está en el vocabulario
   legal del corpus y cuenta como OOV.
2. `_TOKEN_RE` exige ≥4 caracteres, así que **el término real se descarta**: `TON` (3 chars),
   igual que `DIA`, `IPC`, `VI`.

Queda juzgando solo las muletillas → rechaza una query cuyo término SÍ está en el glosario.

**Fix probado:** el diccionario del glosario tiene la última palabra — si `find_term` encuentra
un término definido en el corpus, la query no es off-topic. Es un DATO (la tabla de términos),
no una lista de palabras hardcodeada. Verificado en aislamiento: 5/6 casos, y el que falla
(`"quien gano el mundial de futbol de 1998"`, `oov 2/4 = 0.50`) es un falso negativo
**preexistente**, no introducido por el fix.

**Resultado e2e — pareado, ambos brazos misma sesión:**
```
                     fraseos_v1 (64)              operativas_v1 (114)
cita_ok       62/64 -> 62/64  [1/1]  p=1.0000    96/114 -> 94/114  [2/4]  p=0.6875
rechazos       2/64 ->  2/64                       8/114 ->   9/114   <- SUBIO
cita_limpia   47/64 -> 40/64                      62/114 ->  65/114
precision      0.63 -> 0.58                        0.51 ->  0.54
```
Flat en ambos, y **los rechazos no bajan**. En fraseos ganó exactamente el caso diagnosticado
(`necesito saber qué es TON`) pero perdió otro; neto cero.

**Por qué no sirvió — la causa real de los rechazos:**
```
rechazos en el brazo ON: 9/114
  rechazados por el GATE lexico : 4    <- lo unico que el veto puede tocar
  rechazados por el LLM         : 5    <- el modelo escribe REFUSAL_TEXT por su cuenta
```
**Más de la mitad de los rechazos no vienen del gate**, sino del LLM decidiendo que no puede
responder con los documentos que recibió. Arreglar el gate no los toca. Y de los 4 del gate,
solo algunos nombran un término del glosario.

**Conclusión:** el bug del gate es REAL y el fix es CORRECTO, pero ataca menos de la mitad del
problema y su efecto se pierde en el ruido. `offtopic_glossary_veto` queda **default OFF**.
El frente de los rechazos falsos es de GENERACIÓN (por qué el modelo se rinde teniendo los
documentos), no del gate léxico. Ese es otro experimento.

⚠️ Dato que queda abierto: **8-10 de cada 114 queries operativas reciben un rechazo** (~8%).
Es el modo de falla más visible para el usuario y sigue sin atacarse por el lado correcto.

---

## #48 — La regla #2 fallada por TERCERA vez: el scorer contaba el rechazo correcto como fallo
(2026-08-21)

Iba a gastar 12 h de GPU en el frente de "rechazos falsos" (exp #47 dejó ~8% de las queries
operativas recibiendo "No encuentro esa información"). Antes de correr nada, audité los 9
rechazos. **4 de los 9 eran off-topic legítimos:**
```
cómo hacer un queque de zanahoria · cuál es la capital de Australia
quién pintó la Mona Lisa · qué dosis de paracetamol tomar para la fiebre
```
Son `hold_offcorpus`, con `gold=None`. `exp_lookup_paired` las puntuaba con `cita_ok`, que
exige una cita → **rechazar correctamente contaba como fallo**.

Es la **REGLA #2** del proyecto ("todo scorer nuevo declara cómo puntúa el RECHAZO antes de
correrse"), fallada por tercera vez, ahora en un runner que yo mismo escribí.

**Corregido SIN GPU** — el texto de cada respuesta estaba persistido (regla #5, que existe
exactamente para esto). `scripts/repuntuar.py` re-puntúa las corridas guardadas:

```
                       scorer VIEJO            scorer CORRECTO
gate_noregresion    98/114 ->  99/114      102/114 -> 103/114   [4/3]  p=1.0000
post_reingesta_op   94/114 ->  94/114       98/114 ->  98/114   [3/3]  p=1.0000
veto_operativas     96/114 ->  94/114      100/114 ->  98/114   [2/4]  p=0.6875
off-corpus rechazadas correctamente: 4/4 en los tres, ambos brazos
```

**Ninguna conclusión cambia** (los tres siguen flat), pero el número operativo del sistema
estaba **4 puntos subestimado**: es **~86-90%**, no ~82%.

### Segundo error, dentro de la propia corrección
Mi primer `_es_offcorpus` usaba `gold=None`, y eso mezcla dos casos distintos:
```
hold_offcorpus (4)  "capital de Australia"   -> rechazar ES el acierto
hold_ambiguo   (2)  "qué es la comisión"     -> el termino SI esta en el corpus
```
Las 2 ambiguas aparecían como "el sistema responde MAL"… y sus respuestas eran **correctas**
(Comisión Nacional de Energía, Coordinado). El gold está vacío porque lo esperado es que el
sistema **PREGUNTE cuál acepción**, no que rechace ni que afirme una. Se separa por CATEGORÍA,
no por gold vacío.

⚠️ **Queda medido y sin atacar:** en las 2 ambiguas el sistema **afirma una acepción sin avisar
que hay varias**. Ningún scorer actual lo mide. Es el frente **D4 (UX de ambigüedad)** y, a
diferencia de G4, aquí sí hay casos concretos donde el comportamiento es verificablemente malo.

**Rechazos realmente problemáticos: 5/114 (4.4%)**, no 8%. Y de esos, la mitad viene del LLM,
no del gate (exp #47). El frente es más chico de lo que parecía.

**Fix aplicado a los runners** (`exp_lookup_paired`, `exp_veto_offtopic`): `es_offcorpus()` por
categoría, y si la query es off-corpus `cita_ok = refusó`.

---

## #49 — Clasificador MULTI-CLASE de intención: **NO adoptar** (2026-08-21)

Cierra el pendiente de B2: los 67 ejemplos de regulación · plazo · sanción · cálculo ·
procedimiento estaban escritos desde B2.1 y no alimentaban nada.

```
LOO/CV5 multi-clase: 65/83 = 78.3%   (azar = 16.7%)

por clase        recall  precision   n
  calculo         0.85     0.73     13
  definicion      0.69     0.92     16   <- el gate BINARIO da recall 0.99
  plazo           0.86     0.71     14
  procedimiento   0.77     0.77     13
  regulacion      0.73     0.69     15
  sancion         0.83     1.00     12
```

**Dos razones para no adoptarlo, ambas medidas:**

1. **Es peor que lo que ya hay para lo que ya hace.** `definicion` cae de **recall 0.99**
   (gate binario, exp #43c) a **0.69**. Usar el multi-clase para decidir la inyección
   perdería 3 de cada 10 queries de definición. El binario se queda.

2. **La logreg no salva el multi-clase como salvó el binario.** 78.3% es exactamente lo mismo
   que daba el CENTROIDE en el probe #42 — o sea, acá la regresión logística **no aporta nada**
   sobre el coseno crudo. En el binario subía de 0.982 a 0.990 porque tenía 295 positivos
   (incluía el set primario); acá son ~14 ejemplos por clase y no alcanzan para aprender una
   separación fina entre 6 clases.

Las confusiones son semánticamente coherentes, no ruido: `procedimiento→plazo` (3),
`definicion→regulacion` (3), `regulacion→procedimiento` (2). "Cuál es el plazo del trámite" y
"cómo se tramita" **comparten la respuesta**; el límite entre esas intenciones es difuso también
para una persona.

**Además falta el otro lado:** aunque el clasificador fuera perfecto, no hay estructura de datos
que explotar para las 5 intenciones nuevas. Para `definicion` existe el glosario
(`fragmentos_definicion` → artículo padre), que es lo que hace determinista a `glossary_inject`.
Para `regulacion`/`plazo`/`sancion` **no hay tabla equivalente** — habría que construirla, y eso
es E4 (norma→obligación→proceso), el foso, no un clasificador.

Se guarda `data/intents/intent_multi_v1.json` con los coeficientes y el caveat, para no repetir
el trabajo cuando haya más ejemplos.

**Lo que desbloquearía esto:** queries reales del usuario. 14 ejemplos por clase escritos por el
asistente no bastan, y el sesgo del autor queda horneado en los coeficientes.

---

## #50 — D4 `ambiguity_disclose` **ADOPTADO** (2026-08-21) — el resultado más significativo

```
DECLARA ambiguedad   OFF 18/35  ->  ON 28/35   [gano 11, perdio 1]  McNemar p=0.0063
cita_ok (no romper)      31/35  ->     32/35
cobertura normas          0.65  ->      0.86
normas citadas            1.69  ->      2.29
docs inyectados           0.00  ->      2.51
segundos                 77.71  ->     85.92   (+10%)
```

**p=0.0063** — más significativo que `glossary_lookup` (0.0312), que era el mejor hasta hoy.
Y `cita_ok` no se rompe (31→32).

**Qué ataja.** 35 términos del glosario están definidos en MÁS DE UNA norma. `def_exact`
elegía una con `ORDER BY length(texto) DESC` — criterio arbitrario — y el sistema **afirmaba esa
acepción sin avisar que había otras**. En materia legal eso puede inducir a error: la respuesta
era correcta pero incompleta.

**Por qué funcionó donde fallaron 3 intentos previos.** GEN8b, GEN13-vía-LLM y GEN13-marca
intentaron arreglar el sesgo definición-vs-regulación **pidiéndole al modelo que juzgara**.
Acá el juicio no se delega: `def_exact_all()` trae **todas** las acepciones (dato de la DB), se
inyectan todas marcadas con `_ambiguo`, y el prompt solo las comunica. El modelo no decide si
hay ambigüedad — se la damos resuelta.

Es la misma lección de `glossary_inject`: **ganancias de datos/estructura, no de presentación**.

**Métrica nueva, porque `cita_ok` es ciega a esto.** Con `also_gold` cualquier acepción cuenta
como acierto — por eso en exp #45 los 4 criterios de desempate empataban 64/64. Se mide:
```
declara      la respuesta cita >=2 de las normas que definen el termino
cobertura    fraccion de normas definitorias citadas
```
Set: `data/eval/queries_ambiguos_v1.jsonl` (35 queries; 5 normas: 1 · 4 normas: 5 ·
3 normas: 7 · 2 normas: 22).

**Costo:** +10% de latencia (77.7 → 85.9 s) por los ~2.5 documentos extra inyectados.

**Relación con G4 (exp #45).** G4 buscaba ELEGIR MEJOR entre acepciones y resultó no medible
(el eval acepta cualquiera). D4 **cambia la pregunta**: en vez de elegir mejor, **no elegir** y
declarar las que hay. Resuelve el mismo riesgo legal por el lado que sí se puede medir.

⚠️ Pendiente: 7/35 siguen sin declarar, y 1 se perdió. No se auditó cuáles.

---

## #51 — R5: el regex de fallback **no aporta nada** — sacado del pipeline (2026-08-21/22)

Deuda abierta desde la adopción de `glossary_lookup`: el regex de prefijo quedó como fallback
cuando el diccionario no encuentra término. ¿Aporta algo o es peso muerto?

**Set construido para maximizar la señal:** `queries_sin_diccionario_v1.jsonl` — las **61
queries in_domain donde `find_term` devuelve `None`**, que son las únicas donde el fallback
puede actuar. (46 llegaron a par válido.)

```
cita_ok      OFF 44/46  ->  ON 43/46   [gano 0, perdio 1]  McNemar p=1.0000
inject       OFF  0/46  ->  ON  0/46   <- NUNCA disparo
precision    OFF 0.51   ->  ON 0.56
```

**Era redundante por construcción, y se podía haber deducido:** el regex y el diccionario
consultan **la misma tabla** (`fragmentos_definicion.termino`). Si el diccionario no encuentra
el término, `def_exact` tampoco va a resolver el concepto que extrae el regex — devuelve `None`
por los dos caminos.

La justificación que yo le había dado ("cubre términos que no están en el glosario, ej. Mora")
**era falsa**: precisamente porque "Mora" no está en `fragmentos_definicion`, ningún camino la
resuelve.

**`regex_fallback = False`.** El regex sigue en `retrieve.py` pero no se ejecuta. Documentado
en `docs/reglas-candidatas.md` R5.

**Con esto, el último hardcodeo de clasificación sale del pipeline.** Lo que decide hoy:
```
intent_gate        logreg sobre embeddings   (dato aprendido)
glossary_lookup    diccionario de la DB      (dato)
ambiguity_disclose def_exact_all             (dato)
```

---

## #52 — `filtrar_fuera_dominio` **ADOPTADO** (2026-08-23)

Cierra E1: la frontera del usuario ("todo lo referente a la subgerencia de mercados") pasa de
ser una etiqueta a filtrar de verdad.

**Marcar no bastaba.** Las 33 normas marcadas seguían con sus 1352 fragmentos en el pool,
compitiendo. El filtro se aplica en las DOS patas del retrieval (BM25 y KNN denso 4b_1024).

```
                     OFF          ON
cita_ok           95/114      100/114   [gano 6, perdio 1]  McNemar p=0.1250
cita_limpia       54/114       61/114   (+7)
precision           0.43         0.48
citas unicas        2.82         2.74
inject             3/114        3/114
```

`p=0.1250` es el **piso** de McNemar con 6-1 (harían falta 7-0 para bajar de 0.05). No alcanza
el umbral, pero **todas las señales apuntan igual** y `cita_limpia` sube 7 — la métrica que
venía siendo la más ruidosa de todas (piso de ruido ~30%, exp #44).

**Dónde gana es coherente con el mecanismo** — preguntas coloquiales reales que antes competían
contra la Ley de Tránsito, alcoholes y procedimiento penal por el mismo espacio en el pool:
```
"me cortaron la luz por una deuda que creo mal cobrada"
"cada cuanto me tienen que mandar la cuenta de la luz"
"tengo una planta solar y me sobra energia"
"quien coordina la electricidad"
"ese grupo que resuelve las peleas entre las empresas y el operador"
```

**Contraste con el set de definiciones (exp anterior, `filtro_fraseos`):** ahí salió flat
(58→59, p=1.0). Predicho y explicado: son 64 queries de definición, y las normas ajenas casi
nunca competían por definiciones del glosario. **El filtro sirve para lo operativo, no para lo
definicional** — que es donde el usuario realmente trabaja.

### Corpus con el que se midió (cambió respecto de todo lo anterior)
```
normas       95 -> 108   (+16 del descubrimiento; 39 marcadas fuera en total)
articulos  2978 -> 3235
fragmentos 3907 -> 4288
```
Ingresó la **LEY 20936** (63 artículos) — establece el sistema de transmisión actual y crea el
Coordinador. Es la base legal de las transferencias de mercado y **el corpus no la tenía**.

⚠️ **Caveat de comparación:** este experimento mide OFF/ON del filtro **dentro del corpus nuevo**.
NO mide cuánto aportó agregar la LEY 20936 — para eso haría falta el mismo set contra el corpus
viejo, que ya no existe. Los resultados de experimentos anteriores quedaron obsoletos al cambiar
el pool.

---

## #53 — E4 PILOTO DEL FOSO: mapa de obligaciones (2026-08-23)

Lo único que no se puede construir desde fuera del CEN. Un RAG legal responde *"¿qué dice el
artículo X?"*; esto responde **"¿qué me obliga a hacer, cuándo, y qué se cae si cambia?"**.

### Cómo funciona
`obligacion(articulo_id, sujeto, accion, destinatario, plazo, evidencia)`. El LLM local lee cada
artículo y propone obligaciones; **cada campo se valida contra el texto** antes de guardarse:

```
sujeto      debe aparecer LITERALMENTE en el articulo
evidencia   debe ser cita literal continua, >=10 chars
plazo       si no aparece en el texto, se descarta la fila entera
```
Sin esa validación el mapa sería una alucinación estructurada — se vería igual de convincente y
llevaría a incumplir un plazo real.

### Tres bugs antes de que funcionara
1. `llm.generate()` devuelve `LLMResponse`, no dict. `str(raw)` daba la repr del objeto.
2. qwen3 razona **en inglés y sin cerrar el `<think>`**: 7962 caracteres de monólogo y cero
   JSON, incluso con 3500 tokens de presupuesto.
3. La directiva `/no_think` **no funcionó** — siguió razonando igual.

**Lo que lo resolvió: decodificación restringida por esquema** (`response_format` → `format` de
Ollama, ya soportado en `llm.py`). Con el sampler restringido al esquema, el modelo no puede
divagar. Primera prueba: **8/8 válidas, 0 descartadas**.

### Resultado del piloto (extracción en curso)
```
190 obligaciones · 60 con plazo · sobre 429 artículos candidatos del núcleo de mercados

por sujeto (normalizado)     por norma
   comisión      69            DECRETO 10   190
   coordinador   29
   comité        19
```

**Obligaciones reales del Coordinador, con su plazo, extraídas del articulado:**
```
enviar                                    a más tardar el día 25 de cada mes    [D10 art 149]
calcular Ingresos Tarifarios Reales       mensualmente                          [D10 art 148]
informar resultados de la revisión        primeros 5 días de marzo              [D10 art 165]
realizar reliquidaciones entre Empresas   —                                     [D10 art 165]
remitir                                   27 meses antes del término del periodo[D10 art 13]
determinar e informar las proporciones    quince días                           [D10 art 110]
```
Eso **es** el trabajo de Transferencias de Mercado, y ningún RAG genérico lo tiene.

### Consultas (`scripts/mapa_obligaciones.py`)
```
--sujeto coordinador   ¿qué me obliga a hacer y cuándo?
--plazos               ¿qué vence y en qué fecha?
--impacto <id_norma>   si esa norma cambia, ¿qué obligaciones dependen de ella?
```
El sujeto se normaliza **en la consulta**, no en la tabla: "La Comisión" y "la Comisión" llegan
como entidades distintas porque el literal es lo que sostiene la validación contra el texto.

⚠️ **Pendiente:** el campo `proceso` está vacío. Agrupar obligaciones en procesos (IVTE,
reliquidación, peajes) es el paso que conecta con el monitor: *"cambió la norma X → se rompe el
proceso Y"*. Falta también sujetos basura ("se", "bases técnicas preliminares") que la
validación acepta porque sí aparecen en el texto.
