# Plan de ejecución — todo lo que falta correr

Lista ordenada y ejecutable. Complementa: `arquitectura-y-fases.md` (qué hay hoy),
`plan-observatorio-normativo.md` (por qué), `experimentos-registro.md` (qué ya se probó).

Fecha: 2026-08-17. Estado: `cita_ok` 262/264 en definiciones · E3 hecho · E6 cerrado.

Leyenda: **GPU** = necesita la 3090 libre · **h** = horas estimadas · **dep** = depende de.

---

## BLOQUE 0 — Desbloqueos (sin esto, cosas quedan colgadas)

| # | qué | GPU | h | dep |
|---|---|---|---|---|
| 0.1 | **Token GitHub** (`gh auth login`) → push de 24 commits al PR #12 | no | 0.1 | usuario |
| 0.2 | **Definir frontera del corpus** — qué materias entran para Transferencias | no | — | **usuario** |

⚠️ **0.2 bloquea todo el BLOQUE 2.** Propuesta sobre la mesa: entra si (a) regula
generación/transmisión/distribución/mercado eléctrico, **o** (b) modifica/deroga a una que ya
está dentro. No entra por ser citada de paso.

---

## BLOQUE 1 — Arreglar la MEDICIÓN antes de tocar nada más

Motivo: el set primario son 279 queries de definición que usan **las mismas 3 plantillas que el
regex `_DEF_INTENT`**. El eval se mide contra sí mismo. Todo lo que sigue depende de arreglar esto,
o las mejoras se verán como nulas.

| # | qué | GPU | h | dep |
|---|---|---|---|---|
| 1.1 | [x] **HECHO** (`50522db`) **Set de fraseos variados** — 64q, `queries_fraseos_v1.jsonl`. 2 grupos: A gate no dispara (40q), B gate si pero extraccion rota (24q). — ~60 queries de definición con fraseos que el regex NO cubre ("cómo se define X", "defíneme X", "X definición", "qué entiende la ley por X") | no | 1 | — |
| 1.2 | [x] **HECHO** — **cita_ok 95.3% → 87.5%** (p=0.18, no significativo). `glossary_inject` **0/64 cobertura**. precision 0.66→0.57. Rechazos 1→4. Exp #41 | **sí** | 1.5 | 1.1 |
| 1.3 | **Set operativo como primario** — hoy 112 queries operativas (coloquial 38 + dev 28 + holdout 19) están medidas UNA vez. Consolidar y medir los cambios adoptados ahí | **sí** | 2 | — |

**RESULTADO (2026-08-18, exp #41):** el eval SÍ era circular **en el mecanismo**, pero el
resultado NO estaba inflado. `glossary_inject` (el mayor win del proyecto, +16) tiene
**cobertura 0/64** fuera de las 3 plantillas — y aun así `cita_ok` solo cae **95.3% → 87.5%**
(p=0.18, n=64). El resto del retrieval rescata casi todo. El costo real es **precisión
0.66 → 0.57**: sin inyección el modelo **rocía más para pegarle igual**.

**Número honesto:** `cita_ok` **87.5%** con fraseos naturales sobre términos fáciles (cota
inferior — solo se usaron términos que hoy aciertan). El 98.9% vale **solo** para las 3
plantillas del set primario.

⚠️ **Modo de falla nuevo:** el fraseo induce RECHAZOS (1/64 → 4/64). El sistema contesta "no sé"
a preguntas que con otro fraseo contesta bien. Re-calibrar el gate off-topic contra este set.

---

## BLOQUE 2 — Clasificador de intención (reemplaza el regex)

**Regla del proyecto:** regex NO como mecanismo principal, solo como override final.

| # | qué | GPU | h | dep |
|---|---|---|---|---|
| 2.1 | **Ejemplos por intención** — definición · regulación · plazo · sanción · cálculo · procedimiento (~15 c/u, escritos a mano) | no | 1.5 | — |
| 2.2 | **Clasificador por embeddings** — embeber ejemplos con el qwen3-4b ya cargado; query nueva → coseno → intención más cercana + umbral. Sin llamada al LLM. **Meta medible: `inject` 0/64 → ~64/64 en `queries_fraseos_v1`** | **sí** | 2 | 2.1 |
| 2.3 | **Medir vs regex** sobre 1.1 (pareado). Baseline ya en disco: `data/eval/results/fraseos_v1/` | **sí** | 1.5 | 1.2, 2.2 |
| 2.4 | **Regex como override** solo donde el clasificador falle | no | 0.5 | 2.3 |

**Entregable:** detección de intención que generaliza, y **5 intenciones nuevas** que hoy no
existen. Habilita inyección determinista para lo operativo, no solo para definiciones.

---

## BLOQUE 3 — Corpus (E0-E2): lo que el sistema debería tener y no tiene

| # | qué | GPU | h | dep |
|---|---|---|---|---|
| 3.1 | **Podar 14 normas ajenas** (tránsito, transporte público, obras públicas, procesal penal, insolvencia) + re-medir | no | 1 | 0.2 |
| 3.2 | **Crawler CNE** — NTCO + resoluciones exentas. **Sin la NTCO el corpus no cubre la operación diaria** (fija los plazos del Informe de Valorización, arts. 3-27 y 3-29) | no | 4 | 0.2 |
| 3.3 | **Re-bajar 25 normas modificadas** — el texto guardado puede ser versión vieja. Riesgo real medido | no | 1 | — |
| 3.4 | **Resolver `referencias.destino_norma_id`** (5687 filas sin resolver) → habilita descubrimiento por citación | no | 2 | — |
| 3.5 | **Crawler SEC** (instructivos, oficios circulares) | no | 3 | 0.2 |
| 3.6 | **Crawler CEN** (procedimientos internos, IVTE) | no | 3 | 0.2 |
| 3.7 | **Cierre transitivo** hasta la frontera — 125 candidatas a profundidad 1 | no | 2 | 0.2, 3.4 |
| 3.8 | **Re-indexar + re-medir** todo lo nuevo (embeddings, fragmentos, definiciones) | **sí** | 3 | 3.1-3.7 |

⚠️ Tras 3.8 hay que **recalibrar el gate off-topic** (hoy calibrado solo para energía) y re-medir
`prompt_doc_char_budget` (ya roza el límite con prompts de 50k chars).

---

## BLOQUE 4 — Monitor de cambios (E5): lo que se pidió

| # | qué | GPU | h | dep |
|---|---|---|---|---|
| 4.1 | **Tabla de eventos** (`norma`, tipo, fecha, diff, detectado_en) | no | 0.5 | — |
| 4.2 | **Diff incremental** — re-scrape + comparar `content_hash` y vinculaciones vs lo guardado | no | 2 | 4.1 |
| 4.3 | **Cron** (usar skill `schedule`) | no | 0.5 | 4.2 |
| 4.4 | **Notificación** — qué cambió y qué respuestas del sistema quedaron obsoletas | no | 1 | 4.2 |
| 4.5 | **Filtro de vigencia en retrieval** — no citar derogado, o citar con advertencia | **sí** | 2 | 4.1 |

**Entregable:** *"el 04.11.2024 la ley 21711 derogó el art. 23 del decreto X, que tu sistema citaba"*.

---

## BLOQUE 5 — El foso (E4): norma → obligación → proceso

Lo único que nadie fuera del CEN puede construir.

| # | qué | GPU | h | dep |
|---|---|---|---|---|
| 5.1 | **Piloto con UN proceso** — Informe de Valorización de Transferencias Económicas: qué artículos lo obligan, con qué plazo, qué cálculo | no | 3 | 3.2 (NTCO) |
| 5.2 | **Modelo de datos** proceso ↔ obligación ↔ artículo | no | 2 | 5.1 |
| 5.3 | **Responder "qué se rompe si cambia X"** — cruzar monitor con el mapeo | **sí** | 3 | 4.2, 5.2 |
| 5.4 | **Escalar al resto de procesos** de la subgerencia | no | ? | 5.1-5.3 |

---

## BLOQUE 6 — E6 residual (bajo retorno, hacer solo si sobra tiempo)

| # | qué | GPU | h | nota |
|---|---|---|---|---|
| 6.1 | **GEN13** marcar artículo definitorio | **sí** | — | **CORRIENDO AHORA** |
| 6.2 | **G4 entity resolution** — 42 términos definidos en >1 norma; hoy desempata por `length(texto) DESC`, criterio arbitrario. Riesgo LEGAL | **sí** | 4 | 2.2 ayuda |
| 6.3 | **D4 UX de ambigüedad** — hoy afirma donde debería preguntar ("qué es la comisión") | **sí** | 3 | 6.2 |
| 6.4 | **G9 eval multi-hop** — gate para decidir si G5-G10 (traversal) vale | **sí** | 3 | E3 ✅ |
| 6.5 | **Adyacencia misma norma** — marcar art. siguientes como "desarrollo" | **sí** | 2 | 6.1 |
| 6.6 | **vLLM / llama.cpp + constrained decoding** — mataría el rociado sin las 3 pasadas (61s → ~20s). ⚠️ riesgo: RAM 14GB es el cuello, no la VRAM | **sí** | 6 | — |

**NO hacer** (medido y muerto): pool depth · otro reranker · think=True · híbrido think ·
prompts de rol · recorte de docs · self-consistency N=5 · grafo concepto→artículo crudo.

---

## Orden recomendado

```
0.1 0.2          desbloquear (usuario)
1.1 1.2 1.3      saber el numero REAL          <- antes de tocar nada
2.1 2.2 2.3 2.4  clasificador de intencion
3.1 3.3 3.4      corpus barato (poda, re-bajar, referencias)
3.2              crawler CNE  <- el mas importante del bloque 3
4.1 4.2 4.3 4.4  MONITOR  <- lo que se pidio
5.1              piloto del foso
3.5 3.6 3.7 3.8  resto de crawlers + re-index
5.2 5.3 5.4      escalar el foso
6.x              residual
```

**Racional del orden:** primero saber si el 99.2% es real (BLOQUE 1), porque condiciona todo lo
demás. Después el clasificador (BLOQUE 2), porque habilita lo operativo. Después corpus barato y
la NTCO. El monitor va antes que el resto de crawlers porque es lo que se pidió y ya tiene la
infra. El foso arranca con un piloto, no escalando a ciegas.

**Total estimado sin BLOQUE 5.4 ni 6:** ~40 h de trabajo, de las cuales ~18 h son GPU.
