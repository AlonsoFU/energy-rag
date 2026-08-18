# Backlog UNIFICADO de mejoras (trabajo futuro)

Consolida: (a) research verificado 2026-07-31 (`docs/research-improvements-2026-07-31.md`) +
(b) TODO el trabajo futuro previo disperso en los docs del repo (handoffs, roadmaps, ADRs,
graphrag-roadmap, gap-analysis). Es la **cola activa única** — reemplaza backlogs sueltos.

## Protocolo (OBLIGATORIO por experimento)
1. Flag-gated, default OFF.
2. Medir dev + holdout (caza overfit) + no-regresión vs config vigente.
3. Al terminar: anotar en **HECHO** con Δ medido (dev/coloq/holdout).
4. Si da MEJOR sin regresión → se adopta y **reemplaza la config vigente** (`CLAUDE.md` + flags/`.env`).
   Si no → pasa a **PROBADO — NO repetir** con el nombre.
5. ADR/handoff junto al cambio, no al final.

## ⚠️ REGLA DE ORO (aprendida a los golpes)
**El screen (gold ∈ topN) MIENTE.** Nada se adopta por screen, solo por **cita_ok end-to-end**.
Test para cada item nuevo: *¿esto AGREGA el gold al pool, o solo mete ruido alrededor de un gold
que ya estaba?* (`experimentos-registro.md`, `chunking-rules.md §6`).

## ⚠️ ROBUSTEZ ESTADÍSTICA (los sets chicos NO detectan deltas chicos)
Sets actuales: coloquial **39**, dev **44**, holdout **18** (~101). Ruido binomial ≈ **±2 queries
= 1σ**; holdout ±2 casi inútil. El LLM **flickea ±1** por corrida (verificado). → **Δ≤2 es RUIDO,
NO se adopta.** Los WINs grandes de la campaña (+7, +11) SÍ son reales (~4-5σ); de acá en adelante
los deltas serán chicos (1-3) → hay que endurecer la medición:
- **Set primario `balanced_v2` (339q)**, no coloquial (39q). Más n = menos ruido. (Ya existe.)
- **McNemar pareado** (retrieval/pool fijo → pares): mirar los FLIPS, no 37/39 vs 38/39. Necesitas
  **≥5-6 flips netos** para p<0.05. Reportar qué queries flipean.
- **Gen 2× + promediar** (LLM flickea ±1).
- Gold **se lee de la ley**, NO se deriva del sistema (`CLAUDE.md` principio 3).

Estados: `[ ]` pendiente · `[~]` en curso · `[x]` hecho-adoptado · `[-]` probado-descartado ·
`🏗️` infra existe, sin medir e2e · `❌` ausente · `⏳` diferido.

---

## PRIORIDAD RECOMENDADA (actualizada 2026-08-05 — plan por FASES)

**HECHO esta campaña:** [x] E0/E0b (eval real 84%, no 62%) · [-] M1 (ruido) · [-] G1 crudo (aristas
vacías) · [-] M2/def_fragments/rechunk (flat) · [-] RK1 (Δ+2, dead). Detalle: `campaign-def-recall-2026-08.md`.

**Diagnóstico (2026-08-07, post-E3+E0c; la métrica quedó luego en 97.4% con GEN9a):** cita_ok
contestables 252/267. De las **26 fallas brutas** (`scripts/diag_refusals.py`):
Por origen: 16 RETRIEVAL (gold nunca llegó al pool) + 10 GEN (gold en pool, 6 con **rank=0**).
19 de las 26 son **RECHAZOS** ("no encuentro la norma"), no citas erradas.

**Pero el corte que MANDA es si el artículo gold DEFINE el término o solo lo MENCIONA:**
- **15 REALES** (el gold sí define) → arreglables. `TON`, `DIP`, `DIA` (formato leyenda de
  variable: `SIGLA : descripción` tras "Donde:" — el extractor no lo maneja) + `Reposición`,
  `Informe Definitivo` ×3, `Infracciones graves`, `Tránsito` ×3.
- **12 IMPOSIBLES** → `Gas licuado` ×3, `Acometida` ×3, `Vehículo` ×3, `Empresa distribuidora` ×3
  (11 fallas + 1 acierto espurio por escopeta).  Ya marcadas `unanswerable` (E0c HECHO).
  **El corpus NO define esos términos en ninguna parte** (verificado con 5 patrones: `TERM:`,
  `se entiende por`, `TERM es/será`, `se denomina`, `definición de`). El gold apunta a un artículo
  que solo MENCIONA la palabra. **Rechazar es la conducta CORRECTA y el eval la castiga.** → E0c.

**MÉTRICA VIGENTE (2026-08-08, post-GEN9a): contestables 260/267 = 97.4%** · imposibles:
rechazo correcto 8/12. Quedan **7 fallas**.
⚠️ 5 de las 6 mejoras grandes fueron arreglar el EVAL, los DATOS o un BUG (eval sucio −22 ·
timeouts como False · golds mención-vs-definición · parser de ordinales +7). Solo
`glossary_inject` fue un cambio de sistema. **Ningún cambio de MODELO convirtió nunca.**
**Auditar el gold ANTES de construir el fix.**

### FASE A — exprimir el buscador (local/barato)
1. [x] **glossary_inject** — ADOPTADO 2026-08-05 (default ON). **233→249/279 (+16, 0 pérdidas),
   McNemar p=0.0000.** cita_ok in_domain 83.5% → **89.2%**. Mayor WIN de retrieval de la campaña.
   Ganó más de lo diagnosticado (atacaba 6 glosario, ganó 16): también arregló casos "ranking"
   donde el gold estaba en el pool pero el reranker lo enterraba.
2. [-] **M1 re-test pool=100 sobre eval limpio** — PROBADO 2026-08-06, **MUERTO DEFINITIVO**.
   Pareado limpio (`scripts/exp_m1_paired.py`, ambos brazos misma sesión, glossary_inject ON):
   **OFF 252/279 → ON 252/279, gano 0 perdio 0, McNemar p=1.0000.** 279/279 pares, 0 errores.
   41 top-10 cambiaron y NINGUNO convirtió. El pool NO es el muro; el gold no está en rank 50-100.
   No re-probar con otras profundidades sin una hipótesis nueva.
3. [x] **D2 · extractor formato LEYENDA DE VARIABLE** — HECHO 2026-08-07, adoptado por
   CORRECCIÓN DE DATOS (no por el Δ). `scripts/exp_d2_paired.py` (swap de tablas para el brazo OFF):
   **OFF 252/267 → ON 254/267 (gano 3, perdio 1), McNemar p=0.6250 = NO significativo.**
   Ganó: `definición de TON`, `qué significa TON`, `qué significa Infracciones graves`.
   Perdió: `qué es Proyecto` (con el gold en rank=0 igual → flicker de gen).
   Tabla `fragmentos_definicion` 608 → **713** (+103 símbolos de 20 artículos con leyenda).
   **Se adopta pese a p=0.63 porque son dos correcciones objetivas, no un tuning:**
   (a) BUG en `NOISE`: `Art\.`/`D\.O\.` seguidos de `\b` NUNCA matcheaban (tras '.' viene espacio,
   entre dos no-palabra no hay frontera) → las líneas de enmienda se colaban DENTRO de las
   definiciones y PARTÍAN palabras ('siguiente c'+ruido+'ociente:'), que era justo lo que rompía
   el trigger de TON. Afectaba también al glosario clásico (608→610).
   (b) TON/DIP/DIA están genuinamente definidos ahí y faltaban.
   **CLAVE: tras D2, `rank_gold` = 0 para TON/DIP/DIA — el gold es el doc #1 y la gen igual falla.**
   → el residuo de esas 5 queries es **100% GEN8**, no retrieval. Retrieval quedó óptimo acá.
4. [ ] **G3 fix dedup** `build_candidates` — bug conocido, barato.
5. [ ] **5 coloquiales** — curación manual de aliases (no ingeniería).
   ⚠️ El "techo ~93%" del plan viejo quedó OBSOLETO (se calculó sobre 84%/45 fallas).
   Hoy: **94.4% con 15 fallas atacables** → D2 ataca ~7, GEN8 ataca ~8.

### FASE B — gap de GEN  ✅ CERRADA
- [x] **GEN2 self-consistency N=3 — ADOPTADO 2026-08-10** (`self_consistency_n=3`).
  cita_ok 260→259 (p=1.0 plano) · **cita_limpia 170→188** · **cita_perfecta 85→114** ·
  precisión 0.59→**0.66** · tiempo 20.8→**61.4 s**.
  Único cambio que sube precisión SIN costar aciertos, y el único que rompe el sesgo
  funcional-vs-definitorio (gana Coordinador, Infracciones graves, Energía de Regulación)
  que resistió RK1, `think=True`, híbrido y dos prompts.
- [-] **GEN12 híbrido `think`** — 260→250 (gana 1, pierde 11), p=0.0063 NEGATIVO. Recuperó
  6 de los 16 golds de `think=True`, no alcanza. Los golds no se pierden solo por RECHAZAR:
  también por comprometerse con el artículo funcional, y el reintento no lo detecta.
- [x] **D3 trigger ampliado** (713→**743** frags) — 260→261, p=1.0 flat. Adoptado por
  CORRECCIÓN de datos: convirtió `Reposición` (`1058072/4º`, formato "los recursos que siguen:").
- [x] **E0c ampliado**: `Tránsito` ×3 → `unanswerable` (los golds solo NOMBRAN la ley 18.290).
  Contestables 267 → **264**.

### FASE B (histórico)
5a. [x] **GEN9a · parser de citas con ordinal en palabra** — ADOPTADO 2026-08-08 (bug de producción).
   `CITATION_PATTERN` solo aceptaba `\d+` → `[Art. primero de 1204012]` no matcheaba y
   `strip_malformed_citations` **borraba la cita de la respuesta al usuario**. 267/2978 artículos
   (9% del corpus), 53 formas. **cita_ok 253→260 (+7, 0 pérdidas), p=0.016.**
   Ganó: DIA ×2, Informe Definitivo ×3, DIP ×2 (golds `1204012/primero`, `1160108/segundo`).
   ⚠️ El bug se escondía: el modelo citaba ordinales 0/267 veces en el texto final porque
   `verify_citations` los rechazaba y el retry lo entrenaba a evitarlos DENTRO de la corrida.
   Re-puntuar textos viejos daba +0; solo una corrida nueva lo reveló.
5a2. [-] **GEN9b · prompt de ordinales** — FLAT (260→261, +1, p=1.0). El parser ya bastaba. Flag
   `citation_ordinal_words` queda default OFF.
5b. [x] **E3 auditar efecto escopeta** — HECHO 2026-08-07. **MÉTRICA SANA, no infla.**
   `cita_ok` 253/279 vs `hit_first` 243/279 → solo 11 queries (3.9%) dependen de una cita
   posterior (10 de ellas la 2ª). El 252-253/279 es defendible.
   PERO calidad de cita mala: **precisión media 0.43, mediana 0.33** (143/253 hits con <0.5);
   13.1 citas por respuesta, 4.2 únicas, máx 60. Citar normas erradas junto a la correcta es
   problema legal aunque cita_ok dé True. → causa = GEN8, no la métrica.
   `scripts/exp_e3_shotgun.py` (además PERSISTE el texto de cada respuesta — ningún eval previo
   lo guardaba, por eso no se podía auditar hacia atrás).
5c. [-] **GEN8a `think=True`** (razonamiento en canal separado) — PROBADO 2026-08-08, **NEGATIVO**.
   `scripts/exp_gen8_paired.py`: **cita_ok 254→237 (gano 0, perdio 17)**.
   Calidad de cita SÍ mejora: citas 13.23→2.55, únicas 4.04→1.80, **precisión 0.42→0.64**.
   Coste: +23% de tiempo (19.8→24.4 s).
   Desglose de las 17 pérdidas: **5 VACÍAS** (tecnico, ver abajo) · **2 def alternativa válida**
   (injusticia de eval) · **10 ERROR REAL**. Aun descontando lo demás quedaría 254→244.
   ⚠️ **CAVEAT de configuración (casi lo tomo como resultado):** el 1er intento dio 0/11 porque
   con `think=True` el razonamiento sale del MISMO presupuesto que la respuesta y `num_predict=2000`
   dejaba la respuesta VACÍA (`done_reason=length`, `response=0`). Fix `ollama_num_predict_think=6000`
   → aun así quedan 5 vacías; subir más si se retoma.
   **HALLAZGO: con `think=True` el modelo prefiere el artículo FUNCIONAL sobre el DEFINITORIO**
   (`Infracciones gravísimas` → cita 29819/15 de sanciones en vez del gold 1155887/4 que define;
   `Coordinador` → 258171/212-1). Es el MISMO sesgo del cross-encoder que RK1 no rompió. La
   deliberación en el cuerpo, aunque fea, hacía que enumerara todo e incluyera el artículo inyectado.
5d. [-] **GEN8b · sesgo DEFINICIÓN-vs-FUNCIONAL vía prompt** — PROBADO 2026-08-08, **FLAT**.
   Flag `prompt_prefer_definition` (bloque `PREFER_DEFINITION_BLOCK` en prompts.py, +744 chars):
   **cita_ok 253→254 (gano 2, perdio 1), McNemar p=1.0.** citas 13.19→13.09, únicas 4.04→3.93,
   precisión 0.42→0.43, tiempo igual. **La instrucción NO mueve el comportamiento**: con
   `think=False` el modelo delibera y cita todo lo que mira; decirle cuál preferir no lo frena.
   → El sesgo definición-vs-funcional NO se arregla por prompt. Se arregla en RETRIEVAL con
   inyección determinista (`glossary_inject`, +16). Mismo patrón que RK1: el fix no es el modelo.
5e. [ ] **cita_ok premia ROCIAR** (consecuencia de GEN8a): con 4.04 citas la precisión es 0.42 y
   acierta; con 1.80 sube a 0.64 y falla. El fix de fondo es una MÉTRICA con precisión, no más
   prompt-engineering. Ver E1/E3.
6. [ ] **E1 RAGAS faithfulness** — medir QUÉ falla en gen ANTES de tocar gen.
7. [ ] **GEN6 fix runner** (trivial) + **GEN3 reordering** (barato) + **GEN2 self-consistency** si E1 lo justifica.

### FASE C — table-stakes legal pre-producción
8. [ ] **D1 vigencia** (scrape BCN) — proyecto de DATOS, paralelo, sin GPU. Único error GRAVE del sistema (citar norma derogada).
9. [ ] **R1 metadata filtering** + **GEN5 fallback≠rechazo**.

### FASE D — gate GraphRAG
10. [ ] **G9 eval multi-hop** — gold relacional para DECIDIR si G5-G10 valen. Sin esto no se invierte en traversal.

**Diferido:** FT1/FT2, escala, frontera (referencia).

### ADMIN / limpieza
- [x] **E0c · golds MENCIÓN-vs-DEFINICIÓN** — HECHO 2026-08-07 (`scripts/audit_unanswerable.py`).
  **12 queries in_domain piden definiciones que el corpus NO contiene**: `Gas licuado` ×3,
  `Acometida` ×3, `Vehículo` ×3, `Empresa distribuidora` ×3. El gold apunta a un artículo donde el
  término solo APARECE (1160108/16 "diagrama georreferenciado de la acometida"; 1155887/7°
  "tratándose de vehículos motorizados"), no donde se define. Auditados los 2978 artículos.
  **El sistema rechaza CORRECTAMENTE y el eval lo penalizaba.**
  Marcadas con `unanswerable: true` en `queries_balanced_v2_clean.jsonl` (golds INTACTOS,
  solo metadata). Deben puntuar **rechazo = acierto**, como `off_corpus`.
  **MÉTRICA CORREGIDA: contestables 252/267 = 94.4%** · imposibles: rechazo correcto 8/12.
  (antes se reportaba 253/279 = 90.7% mezclando ambas)
  Se detectó **1 acierto espurio** ("qué significa Empresa distribuidora", 16 citas disparadas):
  el efecto escopeta de E3 SÍ produce falsos positivos, pero es raro (1/279).
  ⚠️ **Dos falsos positivos de la PROPIA auditoría, corregidos antes de escribir** — quedan como
  regla en el script: (a) las siglas llegan sin punto final (`C.O.M.A.`→`C.O.M.A`) y el patrón
  `TERM:` no matcheaba `C.O.M.A.:` → marcaba imposibles siglas SÍ definidas (C.O.M.A, A.V.I,
  V.A.T.T en 1146553/5 y 258171/103); (b) el patrón `TERM es/será` matchea frases incidentales
  ("La Empresa Distribuidora **será responsable de**...") → definiciones fantasma.
  **Auditar el eval exige las MISMAS normalizaciones que usa el eval.**
- [ ] **ADM1 · merge PR #12 a main** — todo vive en `adopt-winners`, nada en main. Cerrar cuando glossary_inject decida.
- [ ] **C2-drop · drop tabla `fragmentos_inciso`** mixta (1248/7141 phi4) — recomendado, deuda vieja (ver C2).

> **Bloqueante legal aparte (D1 vigencia):** citar norma derogada = error grave. Es gap de DATOS,
> no de código. No bloquea M1-M4 pero es prioritario antes de producción real.

---

## RETRIEVAL

- [-] **M1 · rerank 50-100 candidatos** (no top-10). 1 param (`retrieval_pool_depth` al rerank).
  PROBADO 2026-08 (v1, baseline sucio): +3 McNemar p=0.25 = RUIDO.
  **RE-PROBADO 2026-08-06 pareado sobre eval limpio + glossary_inject ON: 252→252, 0 flips,
  p=1.0000. MUERTO DEFINITIVO.** El gold no está en rank 50-100.
- [ ] **R1 · metadata filtering en `search_vector`** (WHERE por norma/tipo/fecha). Hoy recupera del
  corpus entero, sin filtro. Table-stakes a escala. `roadmap-gap-analysis`. ❌ ausente.
- [ ] **R2 · authority_rank_boost** (LEY>DECRETO>RES en fusión). Flag existe, medido FLAT (corpus
  76% LEGAL, mono-tier). 🔬 OFF — **reactivar cuando el corpus sea multi-tier**. `exp-authority-2026-07-16`.
- [ ] **R3 · Query2Doc** (HyDE ADITIVO: concatena pseudo-doc con query original, NO reemplaza).
  Candidato "seguro", prompt listo, nunca implementado. Distinto de HyDE puro. `tecnicas-query-retrieval #2`.
- [ ] **R4 · intent/entity extraction** — prototipo coloquial +1/dev −1 (term drift). Prompt listo.
  🔬 marginal. `tecnicas-query-retrieval #6`.
- [ ] **R5 · router by confidence (bge_max)** en vez de TF-IDF `AdaptiveRouter`. ⏳ idea. `architecture-status §8`.
- [ ] **R6 · bajar umbral router: coloquial→simple cuando embed_4b activo** (evita 3 llamadas LLM
  redundantes de Complex). ⏳ decisión pendiente. `architecture-status 2026-06-16`.
- [ ] **R7 · score-normalization fusion** (vs RRF+length-weight actual). ⏳. `roadmap-gap-analysis`.
- [ ] **R8 · BM25 weight tuning** (`_length_weights` retrieve.py:131). ⏳ barato.
- [-] **RK1 · upgrade reranker bge-reranker-v2-m3 → Qwen3-Reranker-4B/8B** — PROBADO 2026-08
  (screen recall@10): BGE 237 vs Qwen3 239 = Δ+2 ruido, y Qwen3 17× más lento. El reranker NO es
  el muro (ambos ~85% gold@10). NO adoptar. Clase `Qwen3Reranker` queda (RERANKER_KIND=qwen3, OOM-safe).
- [ ] **R9 (dif) · MMR/diversity, self-query (NL→filtros), SPLADE, RAPTOR, CRAG routing** (flag OFF).
  ❌/🔬 estándar-avanzado, diferido.

## CHUNKING

- [-] **M2 · 1 def = 1 fragmento + parent-doc** — PROBADO 2026-08 (`build_def_fragments.py`, 62
  glosarios→608 defs, tabla `fragmentos_definicion`). Inyección RRF (`def_fragments`): −10 (ruido gen).
  Rechunk limpio (`glossary_exclude`, McNemar pareado): +7/−10 p=0.63 FLAT. En dev: +1 p=1.0 flat.
  MUERTO — el RRF desplaza. Infra queda (flags OFF). El fix bueno = `glossary_inject` determinista (ver abajo).
- [ ] **C1 · Contextual Retrieval REAL** — resumen LLM por-chunk del artículo, prepend antes de
  embeder (~3900 chunks, overnight). Hoy `contextual_text` = texto+preámbulo, NO resumen LLM real.
  Nombrado "el próximo recall lift". Relacionado a SAC pero distinto (resumen de ART vs de NORMA).
  ⏳. `architecture-status §4/§7`, `plan-experimentos-2026-06 Fase3`.
- [ ] **M5 · SAC** (resumen de NORMA prepend a cada chunk) — contra cross-doc mismatch. ⚠️ corpus
  ~78 puede no necesitarlo → medir. Research (halving refutado 1-2).
- [ ] **C2 · "rematch justo": inciso + recontextualización LLM** — el único experimento de chunking
  no hecho de forma justa. **DEUDA:** tabla `fragmentos_inciso` MIXTA (1248/7141 con phi4 luego
  matado). Decidir: terminar (~10h) / revertir 1248 / **drop tabla (recomendado)**. `chunking-rules §7`.
- [ ] **C3 · QA metrics chunking** (Coverage@k, Redundancy@k, MRR@k) + deudas: `glossary` chunker
  pierde texto en 10 arts; `_MARK2` falsos positivos en romanos + pierde 29 arts (§/N°/roman);
  `HUGE=3000` sin tunear. ⏳. `chunking-rules §3`.

## GRAPH (el mayor cuerpo de trabajo diferido; master: `graphrag-roadmap.md`)

Estado base: aristas define_termino (222) ✅; norma→norma 0; concepto→concepto 0; sin traversal
query-time; sin community detection; sin router. `graph_boost` existe pero **subalimentado**
(vinculaciones BCN vacías en datos).

- [-] **G1 · grafo concepto→artículo cableado + MEDIDO e2e** — PROBADO 2026-08: las aristas
  `define_termino` art-level están vacías/mal (0/45 fallas tienen arista correcta). G1 CRUDO muerto.
  RENACE bien como `glossary_inject` (abajo) — arista determinista desde `fragmentos_definicion`.
- [x] **G1b / glossary_inject · inyección DETERMINISTA término→artículo** — **ADOPTADO 2026-08-05,
  default ON.** En query de definición, concepto matchea EXACTO un término de glosario → inyecta el
  artículo padre al top-k, sin desplazar (a diferencia de def_fragments RRF). Es GraphRAG-1-salto
  bien hecho. **MEDIDO (McNemar pareado, balanced_v2_clean 279q): 233→249 (+16, 0 pérdidas),
  p=0.0000.** Ganadas: Coordinador, Superintendencia, Ministerio, Cliente, Titular, Solicitante,
  Proyecto, Actividad, Ajustes, Estado Deteriorado, familia Infracciones (gravísimas/graves/menos
  graves/leves ×2 fraseos). Sortea el muro del reranker que RK1 NO pudo romper.
  Flag `glossary_inject`, `vectorstore.def_exact`, `retrieve._definition_concept`.
  **LECCIÓN: contra un cross-encoder que ordena mal, la inyección determinista gana; otro reranker no.**
- [ ] **G2 · seguir cross-references / remisiones** en retrieval (`follow_remissions.py` existe, no
  cableado; ej AVI art48 remite a LGSE 104/118). 🏗️.
- [ ] **G3 · fix dedup `build_candidates`**: `define_termino` debe ganar a `cita` para el mismo
  artículo (hoy guarda `cita`, esconde la definición real → gold errado, ej "Escenario Energético"
  1160108/art2). ⏳ bug conocido, fix documentado. `modelo-datos-conceptos-definiciones`.
- [ ] **G4 · entity resolution / disambiguación** ("mismo nombre = misma entidad" es la falla raíz;
  "Cliente" en decreto 1935 ≠ moderno). Regla: excluir derogado → mismo ámbito → fecha → si no,
  marcar conflicto. **Precede traversal.** `graphrag-roadmap Rev-2 §A` (CRÍTICO).
- [ ] **M7 / G5 · GraphRAG traversal query-time** (Fase 3): multi-concept detection + traversal
  local (relaciones "A vs B"). Para respuestas multi-hop, NO para "def enterrada en 1 art". ⏳.
- [ ] **G6 · query router grafo/vector/inject** (Fase 4, reglas deterministas; grafo NO debe
  dispararse en simples — medido que daña). ⏳.
- [ ] **G7 · aristas norma→norma** (deroga/modifica/cita, Fase 2). ⚠️ mayoría refs FUERA del corpus
  → bajo ROI hasta crecer. ⏳ diferido.
- [ ] **G8 · aristas concepto→concepto** (Fase 5, LLM-extract + verificador verbatim; solo aceptar
  verbatim). ⏳ riesgo alucinación.
- [ ] **G9 · eval multi-hop (Fase 7)** — construir gold relacional para DECIDIR si GraphRAG (fases
  3-6) vale (invertir si recall@k multi-hop <60%). ⏳ **gate de decisión.**
- [ ] **G10 (dif) · global search (Leiden communities + summaries, Fase 6)**, incremental indexing,
  traversal vía CTE recursivo en Postgres (migrar a AGE/Neo4j solo si cuello), covariates. YAGNI.

## DATA / CURACIÓN / CORRECCIÓN LEGAL

- [ ] **D1 · vigencia/derogación** (no citar norma derogada) — **#1 gap legal table-stakes.** Gap de
  DATOS no código: `normas.metadata->>'estado'` vacío (89/95 DESCONOCIDO). Derivar `estado` de scrape
  BCN (`obtxml?opt=7&idNorma=`, campos `derogado`+`FechaDerogacion`) + parsear "Derógase/Reemplázase
  ley N°X" → luego filtro/downrank. Task #101. ❌ **bloqueado en datos. Crítico pre-producción.**
- [ ] **D2 · extractor automático de aliases/siglas** (46→~100): detectores deterministas (glosario
  SIGLA:expansión, "Nombre (SIGLA)", "en adelante X"). ⚠️ auto dio 51 acrónimos pero NO paráfrasis
  coloquiales (muro coloquial NO auto-derivable). `graphrag-roadmap Fase1`.
- [ ] **D3 · lex specialis por ámbito** (desambiguar defs por dominio). ⏳ diferido (corpus casi todo
  energía). `authority-resolution §9`.
- [ ] **D4 · UX de ambigüedad** (query matcha varios conceptos → mostrar opciones, preguntar, NO
  adivinar por posición). ⏳. `authority-resolution §9-B3`.
- [ ] **D5 · aplicar cola de revisión glosario** `glossary/incoming/canonical_review.yaml` +
  focused-definition gating (flag `inject_focused_definition` dormido, gating pendiente). ⏳.
- [ ] **D6 · expandir eval con más pares coloquiales REALES / usar balanced_v2 (339q)** no
  coloquial (39q) → mejor señal. ⏳ parcial. `handoff-07-06`.

## GENERATION ("el cuello real de cita_ok", según varios docs)

- [ ] **GEN1 · head-to-head generador fuerte** (Claude Sonnet vs qwen3:30b-a3b, mismos pools) —
  NUNCA medido directo. ⚠️ rompe "sin API paga" → solo diagnóstico de techo. Ver research frontera.
  `roadmap-gap-analysis`, `handoff-07-10 Fase3`.
- [ ] **GEN8 · loop de deliberación del generador (NUEVO 2026-08-06, prioritario)** — con
  `think=False` qwen3:30b-a3b razona DENTRO del cuerpo de la respuesta y NO converge: medido en
  "qué es Superintendencia" llegó a 2000 tokens todavía deliberando ("pero necesito verificar
  si..."), rociando **28 citas, mayoría duplicadas**. Capado ya con `ollama_num_predict=2000`
  (evita el timeout) pero **la respuesta sigue siendo un monólogo truncado, no una respuesta**.
  Arreglo real: prompt/system que fuerce formato corto, o reactivar think con canal separado.
- [ ] **E3 · efecto ESCOPETA en cita_ok (NUEVO 2026-08-06, riesgo de MÉTRICA)** — `cita_ok` marca
  True si CUALQUIER cita del texto pega con el gold. Una respuesta que dispara 28 citas tiene alta
  probabilidad de acertar por volumen, no por acierto real. **Auditar cuántos de los ~252 aciertos
  vienen de respuestas con muchas citas** (ej >5) y considerar métrica de precisión de citas
  (cita_ok ponderado / primera-cita-correcta). Mismo tipo de falla que el eval sucio: la métrica
  puede estar inflando, no el sistema mejorando.
- [ ] **GEN2 · self-consistency** (N samples + voto) — ataca 4 gen-fails, barato, ausente. ❌.
- [ ] **GEN3 · lost-in-the-middle reordering** — barato, ausente. ❌.
- [ ] **GEN4 · context compression (LLMLingua)** — menos ruido al LLM, ausente. ❌.
- [ ] **GEN5 · fallback-on-timeout ≠ rechazo legal** ("falla técnica" ≠ "norma no existe"). ⏳
  pendiente implementar. `decisiones-arquitectura ADR`.
- [ ] **GEN6 · fix runner full_hit-skip** (`deepeval_runner.py:174` infla bucket "empty"; parcial con
  `eval_always_generate`). ⏳ trivial.
- [ ] **M4 · step-back rewriting** (coloquial↔legal, abstracción). Complemento del alias-map, NO
  reemplazo. GPU ✅. Research 3-0. Residuos coloquiales.
- [ ] **GEN7 (dif) · CoVe, Self-RAG, generator ensemble+judge, NLI groundedness**. ❌ avanzado.

## EVAL / OBSERVABILIDAD / INFRA

- [x] **E0 · robustez de eval (BLOQUEANTE)** — HECHO/ADOPTADO 2026-08. `balanced_v2` (339q) primario
  + McNemar pareado (`exp_e0_baseline.py` resumible). Reveló que el eval MENTÍA: cita_ok in_domain
  real = **84%** (234/279), no 62%. E0b (`audit_golds.py`): 159 also_gold → `queries_balanced_v2_clean.jsonl`.
  El +22 fue 100% limpieza de eval. dev/coloquial/holdout NO estaban subestimados (solo balanced_v2).
- [ ] **E1 · RAGAS/DeepEval faithfulness + context_precision** — hoy solo cita_ok casero, NO
  faithfulness estándar. "La medición más accionable ahora". ❌. `roadmap-gap-analysis #3`.
- [ ] **E2 (dif) · observabilidad** (Langfuse/Phoenix), feedback loop, human-in-the-loop gate,
  provenance/audit trail. ❌ pre-producción.

## FINE-TUNING (raíz, caro, "al final" — orden: curación→set sintético→embedder→reranker→generator)

- [ ] **FT1 · fine-tune embedder** (pares coloquial→artículo, set curado grande, ojo overfit). 0.6B
  dio overfit (v1 +1/v2 −3). ⏳ set grande nunca hecho. Requiere **hard-negative mining (BM25+CE)**.
- [ ] **FT2 (dif) · fine-tune reranker, generator (LoRA/RAFT), Tulio/Patana→embedder chileno**. ❌ último recurso.

---

## NO hacer / PROBADO — NO repetir (descartados, con Δ)

- **HyDE / multi-query** — alucinan cifras, dañan cita_ok (research 0-3). PERO sub-idea abierta:
  "subir top_k para que la recall de HyDE llegue al prompt" nunca resuelta (`handoff-2026-05-30`).
- **DMQR fan-out completo, Mix-of-Granularity (router entrenado)** — research: sobre-ingeniería.
- **inciso/section chunking** (dev +10 screen, e2e NET −2 = espejismo), **small-to-big genérico**
  (64 vs 67), **regla4 cross-ref determinista** (dose-response negativo). `chunking-rules`.
- **citation_repair** (0/6), **concept_inference** (trade-off +3/−1), **selective_reform** (+1/−1),
  **query decomposition/multi-hop** (−2), **graph_boost_all** (overfit +4/−2), **doc2query** (neg),
  **query expansion sinónimos** (rompió off-topic), **fine-tune 0.6b** (overfit), **gemma2:27b** (roto),
  **8B embedder** (trade-off dev+5/coloq−4), **fusión RRF k×peso** (+2% marginal).

## PROBADO — NO repetir (campaña def-recall 2026-08, detalle: `campaign-def-recall-2026-08.md`)
- **M1** pool 50→100: +3, p=0.25 ruido. El gold no está en rank 50-100.
- **G1** grafo concepto→art: MUERTO. 0/45 fallas tienen arista art-level correcta (solo 48/371 la tienen).
- **M2** def_fragments inyección: −10 pero contaminado por ruido de gen (método malo).
- **rechunk** (def_fragments+glossary_exclude, McNemar pareado limpio): **+7/−10, p=0.63 = FLAT**. No adoptar.
- Infra def_fragments queda (flags OFF, 608 fragmentos): sirve, pero muro del reranker la limita.

## Muros identificados (estado final 2026-08)
- **Reranker prefiere FUNCIONAL sobre DEFINICIÓN** (Coordinador 0.9985 vs 0.981) — probado que
  Qwen3-Reranker NO lo arregla (RK1 dead). Es muro de cross-encoders. **RESUELTO 2026-08-05 con
  inyección determinista `glossary_inject` (+16, p=0.0000)**, no con otro reranker.
- **E0b golds** — RESUELTO: 159 also_gold, eval real 84%. Los residuos son 5 coloquiales (muro
  semántico) + acrónimos (D2).

## HECHO / adoptado (esta campaña 3090)
- Embedder qwen3-4B MRL-1024, alias_union, BGE-GPU, gate AND, gen qwen3:30b-a3b. Ver `handoff-2026-07-31.md`.
- Método de eval robusto: balanced_v2 (339q) + McNemar pareado (ver `campaign-def-recall-2026-08.md`).
- **`glossary_inject` (2026-08-05): +16, p=0.0000 → cita_ok in_domain 83.5%→89.2%.**

## REFERENCIA — SI ALGÚN DÍA ESCALO (NO es cola activa)
Deep-research frontera verificado (2026-08-01), detalle: `docs/research-improvements-2026-07-31.md`
sección "vs frontera". Resumen con números:
- **Embedder: YA superas a frontera cerrado** (Qwen3-emb-8B 70.58 #1 MTEB multi > Gemini 68.37 >
  Cohere-v3 61.12 > OpenAI text-emb-3-large 58.93). Truncar 1024 = zona segura. NO es el cuello.
  ⚠️ excepción: Voyage-law-2 (legal-específico) sin probar.
- **Gen frontera NO mueve cita_ok**: escalar LLM no da cita (closed-book Claude Sonnet 4.5 6.8/100,
  Llama 70B≈8B). Retrieval > generador (2510.06999, 2605.14503 peer-reviewed). Rompería "sin API paga"
  por ganancia marginal. Solo diagnóstico de techo, nunca producción.
- ~~RK1 reranker~~ — PROBADO 2026-08: Δ+2 ruido, 17× lento. Ningún upgrade de modelo pendiente
  con retorno real.
- Cuello de escala real = **RAM host 14GB** (HNSW en RAM) + pgvector sin multi-vector indexado
  (VectorChord), **NO la GPU**. LLM denso 70B+ (>24GB) = upside marginal en cita_ok.
- `ROADMAP_ESCALABILIDAD.txt` (abr-26) mayormente obsoleto (pgvector ya en prod).

### B1 — medición honesta (2026-08-18)

- [x] **B1.1 set de fraseos variados** — `data/eval/queries_fraseos_v1.jsonl` (64q, 64 términos,
  2 grupos). Commit `50522db`.
- [x] **B1.2 medir el sistema con fraseos naturales** — exp #41. `cita_ok` **95.3% → 87.5%**
  (gana 2, pierde 7, McNemar p=0.1797, no significativo). `glossary_inject` **53/64 → 0/64**.
  precision 0.66 → 0.57. rechazos 1/64 → 4/64. **El eval era circular en el mecanismo, no
  inflado en el resultado.**
- [ ] **B1.3 set operativo (112q) como primario** — pendiente, no bloqueado.
- [ ] **re-calibrar gate off-topic contra `queries_fraseos_v1`** — abierto por el hallazgo de
  rechazos falsos inducidos por fraseo (4/64).
