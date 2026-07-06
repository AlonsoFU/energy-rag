# Architecture Status — Energy-RAG vs 2026 Meta

> **Última actualización**: 2026-06-29 (RTX 3090 24GB: LLM gen 32B RESCATA 118 + dev +6; restricciones Pascal obsoletas)
> **Branch**: `feat/definition-source-resolver`
> **Doc de campaña**: `docs/campaign-2026-06-01.md`, `docs/handoff-2026-06-06-resultados.md`

---

## ESTADO 2026-06-07 — Stack adoptado + cierre del frente coloquial

### Arquitectura EN el mejor resultado (producción)
Pipeline siempre activo (no son flags):
1. **Retrieval híbrido**: BM25 (tsvector) + vector (**Qwen3-Embedding-0.6B**, 1024-dim, pgvector)
2. **RRF fusion** con peso por largo de query (corta→BM25, larga→vector)
3. **Reranker BGE cross-encoder** (`use_bge_reranker=True`, `top_rerank_override=30`) — el lift más grande
4. **Graph boost** por aristas `define_termino` (alias-aware)
5. **Expansión jerárquica** fragmento→artículo
6. **AdaptiveRouter** (simple vs complejo) + ComplexRetriever (step-back+HyDE+multi-query)
7. **Inyección de definiciones curadas** (`inject_curated_definitions=True`)
8. **Gate off-topic LÉXICO** (`is_off_topic`) + verificación de grounding/citas

Parámetros: `top_k=10`, `pool_depth=50`, `top_rerank=30`.
Números: **dev 37/44 · holdout 17/18 · extremo 17/18 · coloquial 26/39**.

### Probado y NO adoptado (todos los flags quedan OFF)
`semantic_offtopic_gate` (gate por relevancia BGE — trade-off, no generaliza), `selective_reform`
(reform coloquial→legal, +1 wash), `hyde_in_simple` (overfit), `graph_boost_all` (overfit),
`inject_focused_definition` (regresó fraseo), `anchor_*` (decisión de producto), **fine-tune
embedder Qwen3-0.6B** (wash v1 / overfit v2), entity-anchoring (inviable), ColBERT/rerank-wide/
bge-m3/top_k=20 (nulos o peores).

### Frente coloquial — DIAGNÓSTICO FINO de los 13 fallos (de 39)
Los 13 golds EXISTEN en la DB. Desglose por causa real (rank del gold en el pipeline):
- **5 = gate/generación** (gold en rank 1-2, pero rechazado o citó vecino) → NO es coloquial.
  El gate semántico rescata 3-4 de éstas PERO con 2 regresiones reales (72-10, 51) → trade-off.
- **4 = near-miss** (rank 11-17, bajo el corte top-10) → dispersión de retrieval.
- **4 = miss real** (None: 118 tope-ganancia, 1149788/2º tope-paneles, 212 quién-paga-Panel,
  202975/76 dónde-reclamo) → ESTE es el registro coloquial puro (la brecha cotidiano↔legal).

**Conclusión:** el "problema coloquial" real es ~4/39, no 13. Los otros 9 son gate/generación/
dispersión (frentes distintos, más baratos). El residual coloquial duro no se cierra con reform,
entity-anchoring ni fine-tune-chico en este hardware (8GB GPU). Es límite conocido, no bug.

### Auditoría de NOMENCLATURA / calidad de datos (2026-06-07, medido en DB)
Errores de parsing/numeración que pueden estar afectando citas y contaminando el índice:
| patrón | cantidad | riesgo |
|---|---|---|
| Artículos "N X" (bug parser fecha D.O.) | **238** | fantasmas; uno hizo citar la Ley de Tránsito (258171/139) |
| **Ordinal `º` (279) vs grado `°` (164) mezclados** | 443 | **mismatch en cita**: "2º"≠"2°" → acierto cuenta MISS → SUBESTIMA cita_ok |
| Sufijos bis/ter/quinquies | 161 | colisión/dedup si el parser normaliza mal |
| Guion "72-1" | 64 | bug histórico de 4 capas (ya parchado, vigilar) |
| **Normas off-domain ingestadas** | Tránsito 1007469=**456**, sueldos 1199483=**109**, telepeaje 1207690=**56**, 1099982=**24** (~645) | **contaminan** el índice eléctrico (78 normas totales, varias fuera de dominio) |

Los 2 más accionables y GENERALES (no tocan arquitectura):
1. **Normalizar `º`/`°`** (dos chars Unicode distintos) en numeración Y en el matcher de citas →
   puede DESTAPAR aciertos ocultos sin cambiar nada del modelo. Re-medir después.
2. **Filtrar/segregar ~645 arts off-domain** del índice eléctrico (Tránsito/sueldos/telepeaje).

---

## RESULTADOS experimentos 2026-06-08 (gate + retrieval coloquial)

Programa completo ejecutado tras el diagnóstico por etapas. **Un solo win limpio: gate AND.**

| exp | qué | resultado | decisión |
|---|---|---|---|
| **Gate AND** | rechaza solo si léxico Y semántico (BGE) coinciden en off-topic | **coloquial cita_ok 26→30 (+4)**; dev/holdout sin cambio real; **rechazo off-topic intacto**. Verificado en 6 sets: REGRESA_NEG=0, formales no se tocan (AND ⊆ rechazos léxico) | **ADOPTADO 2026-06-08 (default `offtopic_gate_mode="and"`)** |
| Gate semántico solo | max BGE < τ | +2 pero 2 regresiones reales (72-10, 51) | descartado (AND lo supera) |
| Barrido τ | calibrar umbral | NO hay valle limpio: POS p25=0.13, NEG max=0.99 se solapan | justifica el AND, no un τ fijo |
| **doc2query formal** (mT5 español) | expandir BM25 con preguntas generadas | nulo (28→28): mT5 genera registro FORMAL | descartado |
| **doc2query coloquial** (Ollama) | íd. con preguntas coloquiales | nulo: AND exige todas las palabras / OR sepulta el gold (rank 100-955) | descartado — **BM25 no cruza registro** |
| Anchor cita (E7) | anexar cita autoritativa curada | neutral (dev 36→36, holdout 17→17) | sin efecto en estas |

**Mapa de atribución de los 13 fallos coloquiales (por sub-etapa, medido):**
- BM25 **ciego en las 13** (la pata léxica no aporta NADA en coloquial; el embedder carga solo).
- 4 = GATE (gold en rank 1-2, rechazado) → **gate AND los rescata**.
- 2 = RERANKER hunde (embedder top-4/11 → BGE lo baja).
- 4 = RETRIEVAL profundo (embedder rank 50-104, fuera del pool).
- 2 = ambas patas ciegas (hueco de vocabulario real: 118, 212).
- 1 = generación (cita vecino).

**Meta-conclusión:** el registro coloquial profundo derrotó **4 palancas** (reformulación selectiva,
fine-tune embedder, doc2query formal, doc2query coloquial). El embedder denso es el único que cruza
el registro; BM25 es peso muerto en coloquial. El **gate AND** captura el subconjunto donde el
retrieval YA encontraba el gold pero el portero léxico lo botaba. Las 4 deep-miss (118/212/2º/76)
quedan como límite real → solo embedder genuinamente más grande (Qwen3-4B/8B, fuera de hardware).

---

## RESULTADOS experimento 2026-06-15 (embedder 4B — PRIMER WIN de retrieval que CONVIERTE)

**El desbloqueo:** el embedder grande (Qwen3-Embedding-4B) NO estaba bloqueado por hardware
como decía la narrativa previa. fp16 (8GB) no cabe y bitsandbytes 4-bit no corre en Pascal
(sm_61, "no kernel image", igual que BGE) — PERO el **GGUF 4-bit vía Ollama SÍ corre en la
GTX 1080** (~4.9GB, llama.cpp soporta Pascal, igual que el qwen3.5:9b). `ollama pull
qwen3-embedding:4b`, embed por API, vectores 2560-dim. Mea culpa: se archivó como "imposible"
sin agotar la ruta cuantizada.

Flag `embed_4b_dense` (OFF). Columna `fragmentos.embedding_4b` (vector 2560) poblada con
los 3907 chunks (`scripts/embed_4b.py`). KNN exacto seq-scan (`search_vector_4b`); pgvector
no indexa >2000 dim → sin ANN, OK en ~3900 filas. Artefactos: `exp_4b_screen.py` (vector-only),
`exp_4b_gen.py` (generación dos-fases para evitar swap Ollama 4B↔9B).

**Screen retrieval vector-only (gold∈top-N, 4B vs 0.6B):**
| set | top5 | top10 | top20 |
|---|---|---|---|
| coloquial | +6 | **+7** | +7 |
| dev | +10 | +9 | +5 |
| holdout | −2 | −3 | +0 |

**Generación cita_ok (SimpleRetriever híbrido BM25+4B+BGE, top_k=10, 0.6B vs 4B):**
| set | OFF | ON | Δ |
|---|---|---|---|
| **coloquial** (target) | 27 | 30 | **+3** |
| dev | 28 | 30 | **+2** |
| holdout | 16 | 16 | **+0 (sin regresión)** |

**MRL-1024 VALIDADO (2026-06-16, gen eval completo):** truncar el vector a 1024-dim (prefijo
Matryoshka, `l2_normalize(subvector(...,1,1024))`, columna `embedding_4b_1024` + índice HNSW
`vector_cosine_ops`) CONSERVA y supera el win en generación:
| set | OFF(0.6B) | ON(4B-1024) | Δ |
|---|---|---|---|
| coloquial | 26 | 32 | **+6** |
| dev | 27 | 31 | **+4** |
| holdout | 15 | 16 | **+1 (no regresa)** |
Los 3 sets positivos (las diferencias de baseline OFF 26 vs 27 del run 2560 = no-determinismo
Ollama; ON absoluto 32 vs 30). El screen vector-only ya mostró 1024 conserva el pool-gain
(coloquial top10 +5 vs +7 de 2560). Config `embed_4b_dim=1024`. **1024 es la config adoptable a
escala** (HNSW indexable; 2560 obliga seq-scan exacto, no escala a cientos de miles). pgvector tiene
`subvector`+`l2_normalize` nativos → truncar el corpus es 1 UPDATE, sin re-embed. (Bug de medición
corregido: `exp_4b_gen.py` ahora escribe result-{dim}.json, antes 2560/1024 compartían path.)

**Embedder 8B (2026-06-16, `exp_8b_screen.py`, vector-only gold∈top-N):** `qwen3-embedding:8b`
(GGUF Ollama, ~5.5GB GPU, dim 4096, col `embedding_8b`). 0.6B/4B/8B = coloquial top10 26/33/**33**
(target EMPATADO con 4B), coloquial top5 23/29/31, dev top10 26/35/**39** (+4 sobre 4B), holdout
top10 17/14/**17** (8B recupera el −3 vector-only del 4B). **Veredicto: rendimiento decreciente en
el target** — el 8B aporta en formales (dev) y es más "seguro" (no regresa holdout ni vector-only),
pero en coloquial ≈ 4B. **El 4B (dim 512) sigue siendo la config recomendada** (mitad de tamaño que
el 8B, mismo lift coloquial). No se corrió gen eval 8B (ROI bajo para el target).

**Barrido de dim (2026-06-16, vector-only gold∈top10, `exp_4b_dimsweep.py`):** 0.6B / 512 / 1024 /
2560 = coloquial 26/**32**/31/33, dev 26/**36**/33/35, holdout 17/15/14/14. **512-dim conserva el win
completo** (≈ 2560, y en dev lo supera) → **512 es el dim mínimo viable**: indexable HNSW, mitad de
storage que 1024, mismo lift. Recomendado a escala. (Gen eval confirmado a 1024 y 2560; 512 valida
a nivel retrieval, esperado convertir igual por equivalencia con 1024.)

**VEREDICTO: WIN ADOPTABLE (candidato). El PRIMER lever de retrieval que CONVIERTE a cita_ok.**
- Coloquial +3: rescató 79 (acceso líneas), 198 (facturación), 163/164 (compensación), 1149788/2
  (tope paneles) — deep-miss semánticos donde el gold EXISTÍA pero el 0.6B lo rankeaba hondo.
  Perdió 1 (250604/2). 118 ("tope de ganancia"→"tasa de descuento") sigue fallando = muro de
  vocabulario puro, ningún embedder lo cruza (esperado).
- **holdout +0: el −3 del vector-only NO sobrevive al híbrido** — BM25 (términos exactos formales)
  + BGE rerank recuperan las formales que el 4B-denso solo perdía. Confirma por qué el híbrido
  importa: el 4B mejora la paráfrasis, BM25 cubre lo exacto.
- Contradice el meta-finding "retrieval no convierte": acá SÍ, porque el gold entra al **top-5**
  (no solo al pool) y la respuesta es on-target → el LLM lo cita.

**A ESCALA (pendiente de evaluar antes de adoptar en producción):**
- Re-embed del corpus grande (todas las leyes) con el 4B = lento vía Ollama embed (~1 chunk/~0.3s);
  escala lineal, hacer offline en ingesta.
- 2560-dim sin índice ANN (pgvector >2000 no indexa HNSW/IVFFlat) → seq-scan exacto. OK en 3900
  filas, NO a cientos de miles. **Mitigación: truncar MRL (Matryoshka) a 1024-dim** (Qwen3-Embedding
  soporta MRL) → indexable HNSW + comparable al 0.6B en tamaño de vector. Medir que MRL-1024 conserva
  el +3.
- Costo/query: +1 embed Ollama (GPU). Swap con el 9B de generación si ambos en GPU → en producción,
  servir el embedder en CPU o en una 2ª GPU, o aceptar el swap.

**4B en ruta COMPLEJO producción (2026-06-16, `exp_4b_complejo.py`, embed 4B en CPU num_gpu=0
para coexistir con el 9B sin swap):** cita_ok OFF(0.6B) vs ON(4B-1024): coloquial 30→32 (**+2**),
dev 35→36 (**+1**), holdout 17→16 (**−1**). Comparar con SimpleRetriever (coloquial 26→32 +6, dev
+4, holdout +1): el ON absoluto coloquial = **32 en ambas rutas** (mismo techo), pero complejo parte
de un baseline más alto (la expansión LLM ya sube el 0.6B a 30) → delta menor, y ADEMÁS regresa
holdout −1. **CONCLUSIÓN DE ROUTING: con el 4B, rutear coloquial a SIMPLE es estrictamente mejor**
(mismo techo 32, mayor delta, sin regresión holdout) Y más barato (sin los 3 calls LLM de expansión
de complejo). El 4B hace REDUNDANTE la expansión de complejo para coloquial. Recomendación: bajar
el umbral del router para mandar coloquial a simple cuando `embed_4b_dense` esté activo (o medir si
conviene apagar complejo del todo para esta clase).

**Decisión de adopción + commit: PENDIENTE del usuario.**

---

## RESULTADOS experimento 2026-06-29 (HARDWARE: RTX 3090 24GB — LLM gen 32B ataca el muro de GENERACIÓN)

**Cambio de hardware:** GTX 1080 8GB Pascal sm_61 → **RTX 3090 24GB Ampere sm_86**. Verificado:
torch cuda OK (`venv` cu130 + `venv-gpu` cu118), BGE reranker en GPU **0.13s/32pares** (antes CPU
~20-30min/eval), 8B embedder cabe (4.7GB). TODA restricción Pascal (BGE-CPU, sin fp16, sin
bitsandbytes, swap 4B↔9B, "embedder grande no cabe", "LLM tope 9b") quedó OBSOLETA. Flags
`embed_4b_cpu`/`BGE_DEVICE=cpu` ya no aplican. Artefactos nuevos: `scripts/exp_gen_32b.py`,
`scripts/exp_8b_gen.py`, flag `embed_8b_dense`, `vectorstore.search_vector_8b`, `qwen3:32b` (Ollama).

**Exp estrella — LLM gen 32B vs 9b (qwen3:32b, mismos docs cacheados = PURO efecto de generación):**
config retrieval fija (4B-1024 + alias_union, BGE GPU), se genera desde los MISMOS docs con 9b y 32b.
- coloquial 9b=34 → 32b=**35 (+1)** — **118 ("tope de ganancia") RESCATADO** (estaba en GANA): el muro
  residual de 118 era de GENERACIÓN (el gold YA estaba en contexto, el 9b no lo citaba), CONFIRMADO.
- dev 9b=29 → 32b=**35 (+6)** — salto grande en clase formal/definicional (suficiencia, AVI, áreas
  típicas, ERNC, transmisión zonal, plan expansión…).
- holdout 9b=17 → 32b=16 (**−1**) — churn/ruido.
- **NO es dominante estricto:** gana varios pero ROMPE otros (cuenta de luz, paneles/2, conexión línea,
  inscripción holdout) — el 32B elige citas distintas + no-determinismo. Net fuerte donde importa (dev +6,
  118 caído) pero con churn. Two-phase obligado (32b 20GB + 9b 6.6GB no caben juntos en 24GB).
- **Caveat thinking-mode:** qwen3:32b genera formato cita limpio sin basura de <think> (smoke 18s/query
  con carga). Latencia mayor que 9b (~10-15s/query caliente).

**Conclusión de generación:** el LLM grande es palanca REAL para el muro de generación (118 + clase
formal dev +6), antes inalcanzable por hardware. Costo: latencia + churn (rompe algunos). Decisión de
producto: ¿32B para todo, o solo para queries donde el 9b duda? PENDIENTE del usuario.

**Exp 8B embedder vs 4B-1024 (gen completo, `exp_8b_gen.py`, SIN alias, puro embedder, BGE GPU):**
- coloquial 4B=33 → 8B=**29 (−4)** | dev 4B=29 → 8B=**34 (+5)** | holdout 17=17 (+0).
- **8B NO es win: es TRADE-OFF.** Sacrifica coloquial (−4) por formal (+5). El 8B "over-formaliza" →
  mata el registro coloquial. **El 4B-1024 sigue siendo el campeón coloquial** (el frente de la campaña).
  En GGUF el screen vector-only daba 8B≈4B; el gen completo revela el trade-off real. 8B descartado para
  coloquial; podría servir solo en una ruta formal/definicional dedicada.
- **Patrón emergente (routing):** coloquial → 4B-1024 + alias; formal/dev → 8B embed + 32B gen (ambas
  palancas suben dev: 8B +5 y 32B +6). Una arquitectura por-clase podría subir dev fuerte sin tocar coloquial.

---

## RESULTADOS experimento 2026-06-24 (alias_union — vocabulario controlado coloquial→legal, SOBRE el 4B)

Exp #2. Mapa CURADO `{trigger coloquial → término legal}` (`src/pipelines/alias_map.py`),
query-side, determinista, **sin escribir DB** (sortea el bloqueo de permisos de glosario).
Flag `alias_union` (OFF, requiere `embed_4b_dense`). Artefactos: `alias_map.py`,
`scripts/exp_alias_screen.py` (screen), `scripts/exp_alias_gen.py` (gen), `scripts/exp_alias_auto.py` (B-auto).

**Oráculo (motivación):** con el término legal correcto, el gold de 118/212 rankea top-2/top-1
(retrieval funciona; el único gap es NOMBRAR la entidad). El mapa lo hace determinista.

**Diseño (3 piezas, cada una necesaria — medido):**
1. **unión RRF** de [query original + query reemplazada por término legal] en la pata densa 4B.
   `append` diluye (118 quedaba >50); `replace` solo rescata pero ROMPE casos buenos (caso 2:
   8→>50); la **unión** protege Y rescata.
2. **rerank alias-aware**: el alias mete el gold al pool (vec rank 5-8) pero el reranker lo
   BOTABA (puntuaba solo vs la query coloquial; el gold matchea el TÉRMINO, no la frase). Fix =
   rerankear vs `query + término`. Sin esto el rescate NO llega al top-k final (diagnóstico:
   118/212 vec=8/5 fused=8/5 **reranked=None**).
3. alias **correctamente curado** (un alias malo HACE daño: caso 2 con término genérico arrastró
   8→20 hasta corregirlo contra el artículo real).

**Screen retrieval (4B-1024, rank del gold, pipeline completo):** 87 >10→1, 118 >10→1,
212 >10→4 (**RESCATA**), caso 2 (1149788/2) 3→4 (no rompe).

**Gen eval cita_ok (SimpleRetriever, 4B-1024 sin alias vs alias_union):**
- coloquial 32 → **35 (+3)** — ganan 87, 1149788/2, 212.
- dev 31 → 31 (**+0**, sin regresión).
- holdout 16 → 16 (**+0**, sin regresión).

**Residual 118 coloquial ("tope de ganancia"):** retrieval RESCATADO (rank 1) pero gen NO cita →
ahora es muro de **GENERACIÓN**, no de retrieval (el 9b no conecta "tope de ganancia" con art 118).
Frente distinto (prompt/LLM-judge/modelo más fuerte).

**Exp #2-AUTO (¿generaliza sin curar a mano?, `exp_alias_auto.py`):** extracción automática del
corpus por patrones definitorios ("en adelante 'X'", "se entiende por") da **51 pares
legal↔acrónimo** (SEC, VNR, FAIE, NC, SCR…) + 10 términos. PERO **NO cubre** 87/2/212: el corpus
contiene sinónimos/acrónimos LEGALES, NO paráfrasis COLOQUIALES → no hay de dónde aprender
"tope de ganancia"→"tasa de descuento". **El muro coloquial NO es auto-derivable del corpus.**
Mecanismos distintos: auto escala para acrónimos legales; el rescate coloquial necesita curación
a mano (overfit) o tráfico real de usuarios (el verdadero camino a escala).

**CAVEAT overfit:** los 4 alias son a mano sobre el set de eval → +3 coloquial es prueba de TECHO,
no de generalización. Adoptar `alias_union` rinde en producción solo si los triggers se amplían
con queries reales; el bloque a mano NO debe crecer ad-hoc por cada falla.

**Decisión de adopción + commit: PENDIENTE del usuario.**

---

## RESULTADOS experimento 2026-06-13 (concept_inference — frente RETRIEVAL coloquial)

Estándar legal IR 2025 (STARD / "razonar el concepto implícito"): el LLM infiere los
TÉRMINOS técnico-legales EXACTOS de una query coloquial (corto, anti-alucinación: se
filtran números de ley/decreto inventados) y se añaden ADITIVO vector-only a la query.
Distinto a `selective_reform` (parafraseo verboso que alucinaba "Ley 20.383", "Código
Eléctrico"). Flag `concept_inference` (default OFF). Artefactos: `expansion.infer_legal_concept`,
`scripts/exp_concept_inference.py` (screen retrieval) + `exp_concept_inference_gen.py` (generación).

**Screen retrieval-only (SimpleRetriever, gold∈top-N, ON vs OFF):**
| set | top5 | top10 | top20 |
|---|---|---|---|
| coloquial | 24→24 (+0) | 28→**31 (+3)** | 33→35 (+2) |
| dev | 34→36 (+2) | 36→**40 (+4)** | 40→41 (+1) |
→ WIN de retrieval, **sin regresión**. Rescató coloquial 79/198/163 (concepto cruzó el
registro). PERO **top5 +0**: el gold entra al pool, no al top-5 → la generación necesita top_k=10.

**Generación (AdaptiveRetriever producción, top_k=10, cita_ok ON vs OFF):**
| set | OFF | ON | Δ |
|---|---|---|---|
| **coloquial** (target) | 29 | 28 | **−1** |
| dev (formal) | 36 | 39 | **+3** |
| holdout | 17 | 17 | +0 (sin regresión) |

**Veredicto: TRADE-OFF, NO adoptar para coloquial (flag queda OFF).**
- **El +3 de retrieval coloquial NO convierte a cita_ok; regresa −1.** Confirma el meta-finding
  (N+2): en coloquial la respuesta del LLM se construye sobre el artículo equivocado (el gold,
  recién metido al pool, no es sobre lo que el LLM redactó) → no lo cita; y cambiar el pool
  DESPLAZA alguna cita que antes acertaba → −1.
- **Sí ayuda la clase FORMAL (dev +3):** ahí la respuesta es on-target, el gold que entra al pool
  SÍ se cita. Es palanca de clase formal, no de coloquial.
- **118 nunca flipeó** ("tope de ganancia"→"Tarifa regulada/Ganancia máxima", nunca "tasa de
  descuento") → muro de vocabulario confirmado irreducible aun razonando el concepto.

**META-CONCLUSIÓN (3 frentes agotados):** retrieval-embedder (swap/ensemble/fine-tune),
generación-citation_repair, y ahora concept_inference — los tres mejoran piezas pero NO cierran
coloquial. El cuello es estructural: en coloquial duro el gold o no entra al pool (deep-miss /
muro vocabulario) o, si entra, la generación no lo cita porque redactó sobre otro artículo.
Palancas vivas no probadas: (1) embedder genuinamente más grande OFFLINE (Qwen3-Embedding-4B,
no cabe inline, ~6-10h re-embed), (2) glosario curado manual para el muro de vocabulario (118).

---

## RESULTADOS experimento 2026-06-10 (citation_repair — frente de GENERACIÓN)

Tras agotar el frente de retrieval, se atacó el **cuello de generación** (gold en el pool pero el
LLM cita el artículo vecino). Estándar 2025: **CiteFix** (ACL industry) / **VeriCite** — corrección
de cita post-hoc. No hay modelo NLI offline (HF_HUB_OFFLINE=1) → se implementó la **variante
similarity** reusando el cross-encoder `bge-reranker-v2-m3` ya cargado: tras generar, puntúa
RESPUESTA↔cada doc del pool y AÑADE la cita del doc que mejor la sostiene si no estaba citada.
Propiedad de seguridad: SOLO añade → cita_ok monótona (no puede regresar). Flag `citation_repair`
(default OFF). Diseño eficiente: 1 generación + barrido de umbral post-hoc gratis.

| set | n | baseline | repair (thr≤0) | Δ | changed | precisión añadidas |
|---|---|---|---|---|---|---|
| **coloquial** (target) | 39 | 24 | 24 | **+0** | 3 | **0/3** |
| **dev** (formal) | 44 | 32 | 34 | **+2** | 8 | **2/8 (25%)** |
| **holdout** | 18 | 15 | 15 | **+0** | 0 | — |

**Por qué NO sirve (medido, decisión = NO adoptar; flag queda OFF):**
1. **Coloquial +0 = el fallo NO es de cita, es de retrieval+respuesta.** En las fallas el LLM ya
   citó el doc que mejor matchea su PROPIA respuesta (top_score 0.99, `changed=False`), pero ese
   doc no es el gold: el gold **no está en el top-5** (deep-miss), así que el LLM redactó sobre el
   artículo equivocado y lo citó fielmente. Repair no puede tocar eso (la cita SÍ corresponde a la
   respuesta; lo que está mal es la respuesta). Un pool más ancho NO rescata: la respuesta habla de
   otro artículo → BGE(respuesta, gold) sería bajo igual.
2. **Dev +2 pero precisión 25%.** El +2 costó **6 citas espurias** (4× más ruido que señal). En un
   sistema legal, añadir artículos equivocados = el riesgo de "post-racionalización" que advierte
   *Correctness is not Faithfulness* (SIGIR 2025). Inaceptable.
3. **El score BGE (0-1) no separa gold de hermano plausible** (añade no-gold con 0.975-0.995, igual
   que el gold). **Ningún umbral arregla la precisión** (thr>0 → 0 cambios porque los scores se
   amontonan en 0.9-1.0). Un NLI puro (entailment) lo haría mejor, pero no hay modelo NLI offline.

**Meta-conclusión:** el frente de generación con **similarity** también se agota. El cuello real de
coloquial NO es la elección de cita (eso solo aplica a la clase formal/dev, donde repair da +2
marginal con precisión mala) sino que **el gold no entra al pool** (retrieval deep-miss / hueco de
vocabulario). Confirma la línea: el residual coloquial es límite de retrieval+hardware, no de
post-proceso. Artefactos: `src/pipelines/citation_repair.py`, `scripts/exp_citation_repair_eval.py`,
`data/eval/results/citation_repair/`. Flag-gated default OFF, producción intacta.

---

> **NOVEDAD 2026-06-01 (histórica)**

Este documento mapea el estado actual del pipeline RAG contra el "meta" de
industria 2026 (lo que usan Glean, Perplexity, Cohere, Anthropic API).

> **NOVEDAD 2026-06-01 — GAP CRÍTICO #1 (reranker) RESUELTO.** El cross-encoder
> `bge-reranker-v2-m3` fue validado en campaña con set held-out: recall@5 dev
> 25→33, holdout 15→17; cita_ok (generación) dev 25→**32**, holdout 14→**17**
> con top_k=10; **grounding intacto** (43/44, 18/18). Cableado flag-gated
> (`use_bge_reranker`+`top_rerank_override`, OFF por default). Ver §8.
> HyDE y graph_boost_all se DESCARTARON por overfit (el held-out lo reveló).

---

## 1. Pipeline meta — esquema completo con status

```
═════════════════════════════════════════════════════════════════
   META 2026 — PIPELINE RAG INDUSTRIA ESTÁNDAR
═════════════════════════════════════════════════════════════════

USUARIO escribe query
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. QUERY UNDERSTANDING                                       │
│ ────────────────────────────                                 │
│ ⚠️  Adaptive router: SimpleRetriever vs ComplexRetriever     │
│ ⚠️  HyDE / multi-query / step-back   ← solo en "complejo"    │
│                                          (raramente activado) │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. RETRIEVAL — HYBRID SEARCH                                 │
│ ────────────────────────────                                 │
│ ✅ BM25 (tsvector Postgres)                                  │
│ ✅ Dense vector (Qwen3-Embedding + pgvector HNSW)            │
│ ✅ RRF fusion → top 50                                       │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. CROSS-ENCODER RERANKING  ✅ RESUELTO (2026-06-01)         │
│ ────────────────────────────                                 │
│ ✅ bge-reranker-v2-m3 (CPU; Pascal sm_61 sin kernels GPU)    │
│ ✅ get_reranker(): BGE si use_bge_reranker, si no Identity   │
│ ✅ top_rerank_override≈30 (el rerank cortaba el pool a 10    │
│    ANTES del boost → ahora deja sobrevivir el gold profundo) │
│ ⚠️  Default OFF (costo: latencia CPU ~+seg/query)            │
│ Medido: cita_ok dev 25→32, holdout 14→17; grounding intacto  │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. CONTEXTUAL CHUNKS  ⭐ GAP CRÍTICO #2                      │
│ ────────────────────────────                                 │
│ ⚠️  Columna `contextual_text` EXISTE en DB                   │
│ ⚠️  Hoy: contextual_text = text + preamble                  │
│      (no es contextual real)                                 │
│ ◯ Falta: para cada chunk, generar resumen del doc completo  │
│   con LLM y prependerlo al chunk antes de embeddear         │
│                                                              │
│ Lift esperado: +5 a +10 pp recall                            │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. GRAPH BOOST                                               │
│ ────────────────────────────                                 │
│ ✅ Tabla `referencias` con 4,300 edges                       │
│ ✅ graph_boost() multiplica score por tipo_relacion          │
│ ✅ Concept extraction usa aliases del glosario               │
│ ⚠️  Domain filter activado pero no testeado en eval         │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. HIERARCHICAL EXPANSION  (potencial: parent-doc)           │
│ ────────────────────────────                                 │
│ ⚠️  Existe pero solo expande chunks → artículos parciales   │
│ ◯ Mejora posible: parent-doc retrieval completo             │
│                                                              │
│ Lift esperado: +3 a +10 pp queries descriptivas              │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. ANSWER GENERATION                                         │
│ ────────────────────────────                                 │
│ ✅ Constrained decoding (JSON schema enum de citas)          │
│ ✅ Few-shot prompts (3 ejemplos)                             │
│ ✅ Retry-on-fail con initial_top                             │
│ ✅ Ollama qwen3.5:9b local                                   │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. ANTI-HALLUCINATION                                        │
│ ────────────────────────────                                 │
│ ✅ Grounding verifier: cada cita verbatim contra docs        │
│ ✅ Reject + retry si falla                                   │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
USUARIO recibe respuesta con citas
```

---

## 2. Resumen de posición por capa

| Capa | Status | Notas |
|---|---|---|
| **Foundation** (BM25 + dense + RRF + grounding) | ✅ **Completo** | Al nivel del meta |
| **Cross-encoder reranking** | ✅ **Resuelto (flag, OFF)** | bge-reranker-v2-m3 validado: +cita_ok dev 25→32 / holdout 14→17, grounding intacto. CPU. |
| **Contextual chunks** | ⚠️ **Estructura sin contenido** | Columna existe, hoy = text + preamble |
| **Graph augmentation** | ✅ **Avanzado** | Tabla `referencias` con 4,300 edges, una de las cosas más adelantadas del proyecto |
| **Generation con citas** | ✅ **Completo** | Constrained decoding + verifier verbatim |

---

## 3. Métricas actuales (post-Sprint 1+2+3 + SemanticChunker)

Eval completa 50 queries (`data/eval/results/20260512T180156Z.json`):

| Métrica | Baseline 2-may | Post-Sprint 12-may | Δ |
|---|---|---|---|
| recall@5 (norma+articulo) | 95.8% | 93.8% | -2.0 pp |
| recall@5 (norma) | 95.8% | 95.8% | 0 |
| grounding_pass | 70.8% | 66.0% | -4.8 pp |
| negative_correct | 100% | 50.0% | -50 pp |
| latency p50 | 44s | 35.5s | -19% (mejor) |
| n_with_generation | 48 | 47 | -1 |

Eval queries-con-aliases 15 queries (`data/eval/results/20260512T004231Z.json`):

| Métrica | Pre-chunker | Post-chunker v2 | Δ |
|---|---|---|---|
| recall@5 | 13.3% | 46.7% | **+33.4 pp** ⭐ |
| grounding | 100% (de 2) | 100% (de 7) | 3.5× más queries acertando |

**Tradeoff observado**: el SemanticChunker mejora drásticamente queries cortas
(aliases, conceptos puntuales) pero degrada queries descriptivas largas. El
Sprint completo es mejora local + regresión global.

---

## 4. Próximos pasos al meta — ranking por ROI

| # | Acción | Effort | Lift esperado | Riesgo |
|---|---|---|---|---|
| 1 | **Reemplazar reranker** Qwen3 → bge-reranker-v2-m3 | 1-2 h | +5 a +15 pp grounding | bajo — sin re-ingest |
| 2 | **Contextual Retrieval real** (LLM genera resumen de doc para cada chunk) | 4-6 h cómputo Ollama | +5 a +10 pp recall | bajo — re-ingest 3,318 chunks |
| 3 | **Parent-doc retrieval** completo en `hierarchical_expand` | 2-3 h | +3 a +10 pp queries descriptivas | bajo — sin re-ingest |
| 4 | **GraphRAG** sobre tabla `referencias` (caminos de 2-3 saltos) | 3-5 días | +5 a +15 pp queries complejas | medio — refactor |

---

## 5. Frontera 2026 que NO recomiendo todavía

| Técnica | Por qué no |
|---|---|
| **ColBERT / late interaction** | Sería gran ganancia pero requiere modelo distinto y re-índice completo (5-7 días). Ataque cuando los pasos 1-3 estén hechos. |
| **Long-context LLM** como reemplazo (Gemini 2M, Claude 200k) | Tu sistema es local-first sin API paga. No aplica. |
| **Generative retrieval (DSI)** | Research, no production-ready. |
| **Self-RAG / Adaptive RAG** | +2-5 LLM calls por query, latencia 2-3× actual. Considerar después de los pasos 1-3. |

---

## 6. Tabla de cambios aplicados en Sprint 2026-05-04 a 2026-05-12

Lista cronológica de commits en `feat/postgres-rag-v1`:

| Commit | Cambio |
|---|---|
| `f9056bb` | Auto-validate 23 high-confidence aliases (Fase 1 glosario) |
| `4f6615c` | Promote 18 medium aliases post-WebSearch (Fase 2) |
| `f532be4` | Reranker init fix (pad_token, logits shape) — quedó como identity |
| `b43fe3b` | Reranker → identity rerank explícito (post-eval regression) |
| `141b058` | Sprint 1+2+3 (#1, #2, #3, #5, #7, #8, #10) |
| `1fdb66b` | SemanticChunker v1 + re-ingest 279 articulos (introdujo regresión) |
| `b4fa949` | SemanticChunker fix: `;` como sentence boundary (+33pp recall en aliases) |

---

## 8. Pipeline vigente (lógicas y algoritmos) — actualizado 2026-06-03

Orden real de ejecución de una query (rama `feat/definition-source-resolver`):

1. **Off-topic gate**: rechazo pre-LLM de queries fuera de dominio. Dos modos:
   - Léxico (default, `off_topic.is_off_topic`): si las palabras significativas de la query no
     están en el vocabulario del corpus → rechazo. Barato pero rechaza mal lenguaje COLOQUIAL
     in-domain ("se corta la luz"→no nombra el término legal).
   - **Semántico** (`semantic_offtopic_gate`, flag OFF, 2026-06-03): rechaza si el mejor score BGE
     del pool < `offtopic_bge_threshold`. Arregla los falsos rechazos de coloquial (+2 v3, 0
     regresión). Requiere `use_bge_reranker`. Ver `docs/campaign-2026-06-03.md`.
2. **Router** (`AdaptiveRouter`, TF-IDF + LinearSVC): clasifica `simple` vs `complejo`.
   - `complejo` → `ComplexRetriever`: expande con **HyDE + step_back + multi_query** (LLM local)
     y fusiona por RRF sobre todas las variantes. (OJO: HyDE aquí es del Complex, distinto del
     flag `hyde_in_simple` que se DESCARTÓ por overfit.)
   - `simple` → `SimpleRetriever`.
3. **Retrieval híbrido** (ambas ramas): **BM25** (tsvector) + **denso** (Qwen3-Embedding-0.6B,
   pgvector HNSW) → **RRF fusion** ponderada por largo de query (`_length_weights`: query corta
   pesa BM25, larga pesa vectores). Pool = `retrieval_pool_depth` (50).
4. **Rerank** (`get_reranker`): **NUEVO** — `BGEReranker` (cross-encoder bge-reranker-v2-m3, CPU)
   reordena el pool por relevancia semántica query↔doc cuando `use_bge_reranker=True`; si no,
   `IdentityReranker` (preserva orden RRF). `top_rerank_override` (≈30) controla cuántos
   candidatos sobreviven a esta etapa (antes 10 fijo → truncaba el gold profundo).
5. **Concept extraction + graph_boost**: detecta conceptos del glosario en la query y sube los
   artículos con arista `define_termino`/`cita` a esos conceptos. El boost fuerte (+10) aplica a
   match por **alias**; `graph_boost_all` (extenderlo a match canónico) se PROBÓ y DESCARTÓ (overfit).
6. **Hierarchical expand**: fragmento → artículo padre.
7. **Inject curado** (`inject_definition`, solo queries definicionales "qué es X" con match exacto
   de concepto): antepone el artículo-definición curado, aun si retrieval lo perdió. Legal-safe
   (normalización estricta, aristas curadas). Para alias inyecta el link «alias»→«canónico».
8. **Generación** (`generate_answer`, Ollama qwen3.5:9b, top_k=10 recomendado): prompt few-shot;
   patrón híbrido (sin JSON-schema, que deadlockea en Ollama) + **verify_citations** post-hoc.
9. **Anti-alucinación**: cada cita se verifica verbatim contra el pool; si falla, retry con
   instrucción más estricta; fallback a verificación contra corpus (existe (norma,art) en DB).
10. **Anchor determinista** (`_anchor_authoritative_citation`, flag OFF): si la query centra en
    un concepto con artículo autoritativo A y la respuesta no citó la norma de A, anexa la cita
    curada. Monótono sobre cita_ok.

**Config recomendada por la campaña**: `use_bge_reranker=True` + `top_rerank_override=30` +
`--top-k 10`. Descartados por held-out: `hyde_in_simple`, `graph_boost_all`, **term-prefix de
glosario** (2026-06-02: net≈0, held-out no mejora, regresión por competencia entre glosarios),
**swap embedder bge-m3** (2026-06-03: mismo tamaño que Qwen3-0.6B, no ayudó coloquial 5/11=igual,
−2 neto, revertido). **Registro completo de técnicas de query/retrieval: `docs/tecnicas-query-retrieval.md`.**

**Frentes documentados sin hacer** (`tecnicas-query-retrieval.md`, `handoff-2026-06-02.md`):
intent/entity extraction (#6, próximo lever de query), embedder más grande (Qwen3-4B/8B; 8B no entra
en GTX 1080), fine-tune Tulio/Patana (específico), router por confianza (bge_max) vs el TF-IDF actual.
Nulos: pool_depth>50, BGE max_length>512.

## 8b. Registro de límites de hardware (distinguir "bloqueado" de "solo más lento")

**RESUELTO 2026-06 — BGE/embedder en GPU** (era "bloqueo duro", se desbloqueó sin hardware nuevo):
- El torch del venv principal (**2.11+cu130**) NO soporta Pascal sm_61 → embedder y BGE caían a CPU
  (solo Ollama usaba la GPU). NO era la GPU ni el modelo: era el build de torch.
- **PROBADO**: `torch 2.7.1+cu118` (trae PTX sm_60 → JIT a sm_61) corre **BGE en la GTX 1080**:
  30 pares en **0.16s** (vs minutos en CPU). La latencia de BGE —único costo de adoptarlo— DESAPARECE.
- Instalado en venv aparte `venv-gpu/` (gitignored) para no tocar el venv principal.
- **COEXISTENCIA PROBADA (fp16)**: el techo real no era torch sino la **VRAM (8GB)**. Solución:
  BGE en **fp16** = **1.16 GB** (vs ~2GB fp32, calidad ranking ~igual: score 0.989 vs 0.997).
  Query real end-to-end: **9b (5.9GB) + BGE fp16 (1.8GB) = 7.75 GB / 8 GB, SIN OOM**, embedder
  en CPU. Respuesta correcta citando el art gold. Margen ~450MB (ajustado pero estable; vigilar
  con contextos largos).
- **Config GPU (en `venv-gpu`)**: `USE_BGE_RERANKER=1 BGE_DEVICE=cuda BGE_FP16=1 EMBEDDER_DEVICE=cpu`
  + `--top-k 10`. El venv principal (cu130) NO puede usar la GPU para torch → se queda con BGE en CPU.
  Wiring: `BGEReranker` usa fp16 cuando `BGE_DEVICE=cuda` (`src/components/reranker.py`).
- **VALIDADO end-to-end (84 queries, 3 sets, 2026-06)**: cita_ok dev **32/44** (= CPU fp32, sin
  regresión), holdout **16/18** (vs 17 = ruido Ollama; grounding 18/18), extremo **14/18** (grounding
  18/18, 4/4 rechazos off-corpus). **0 OOM** en las 84 queries → la config GPU 7.75/8GB es estable.
  fp16 NO degrada la calidad de citas; la latencia de BGE desaparece. Recomendado para uso real.

**Solo MÁS LENTO** (corre en CPU/tarda más → se mide igual, la latencia es dato de costo, no bloqueo):

| Lever | Hipótesis | Costo hoy | Acción |
|---|---|---|---|
| ~~**BGE `max_length` 512→2048**~~ | ~~cubre el ~30% de chunks truncados~~ | — | **PROBADO NULO (2026-06)**: 512≈1024 en dev+extremo; `ext_hundida` ya 6/6 a 512. El retrieval es POR CHUNK (cada def vive en su fragmento chico) → el truncado no pierde respuestas. El stat "30% truncado" era real pero engañoso. NO adoptar. |
| **Contextual chunks (gap #2)** | resumen del artículo por LLM antepuesto a cada chunk → +recall en paráfrasis | re-ingesta ~3.900 chunks = horas Ollama | PENDIENTE el resumen LLM full; la variante barata (term-prefix determinista de glosario, 88 chunks) se PROBÓ y DESCARTÓ 2026-06-02 (ver campaign-2026-06-02). Insight: el cuello es generación/cita, no recall |
| **Re-chunk glosario fino (art 225)** | 1 def = 1 fragmento → cada def cabe entera en el reranker | re-ingesta + re-embed | medible (lento, no bloqueo) |

## 7. Conclusión

**Estás más cerca del meta de lo que parece.** La foundation es sólida (hybrid
search, grounding verifier, glosario curado, referencias graph).

- ✅ **Gap #1 (reranker) RESUELTO** (2026-06-01): bge-reranker-v2-m3 validado con held-out,
  +cita_ok sin perder grounding. Flag-gated (OFF). Falta decisión de producto por la latencia CPU.
- ◯ **Gap #2 (Contextual Retrieval real)** sigue pendiente: hoy `contextual_text` = text + preamble.
  Es el próximo lift de recall (resumen del artículo por LLM, antepuesto al chunk antes de embeddear)
  — ataca directo el fallo "operativo no glosario / paráfrasis no matchea".

**Lección de método de la campaña**: medir SIEMPRE en un set held-out independiente (gold leído de
la ley, no del propio sistema). Reveló que HyDE y graph_boost_all eran overfit — habrían sido
adoptados mirando solo el set de desarrollo.
