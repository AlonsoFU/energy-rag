# Arquitectura actual + plan por fases

Documento único de referencia: **cómo está construido el RAG hoy**, **en qué fase del proyecto
estamos** y **qué falta**. Complementa `plan-observatorio-normativo.md` (el porqué) y
`experimentos-registro.md` (la evidencia).

Fecha: 2026-08-16.

---

# PARTE A — Cómo está construido el RAG actual

## A.1 Datos en Postgres

```
normas                  95     las normas descargadas de BCN
articulos             2978     el articulo es la UNIDAD DE CITA ([Art. N de ID])
fragmentos            3907     chunks para busqueda (un articulo puede partirse)
fragmentos_definicion  743     1 definicion = 1 fragmento (glosarios + leyendas de variable)
conceptos              371     terminos legales canonicos
referencias           5687     articulo->articulo (destino_norma_id SIN RESOLVER)
norma_vinculacion      204     norma->norma desde BCN (modifica) -- NUEVO
aliases_aprendidos       0     vacio (los alias vivos son a mano en alias_map.py)
```

## A.2 Pipeline de una consulta

```
QUERY
  │
  ├─ 0. GATE off-topic (AND: lexico + BGE)   -> si no es del dominio, RECHAZA
  │
  ├─ 1. BM25            (tsvector, terminos originales)
  ├─ 2. VECTOR          (qwen3-embedding:4b truncado MRL a 1024-dim, HNSW)
  │      + alias_union: si la query es coloquial, se agrega la version legal como 2a query
  │
  ├─ 3. RRF             fusion ponderada por largo (query corta->BM25, larga->vector)
  ├─ 4. RERANK          BGE cross-encoder (bge-reranker-v2-m3) en GPU, pool 50
  ├─ 5. CONCEPTOS       deteccion + filtro de conceptos fuera de dominio
  ├─ 6. GRAPH BOOST     (subalimentado: las aristas concepto->articulo estan vacias)
  ├─ 6c. GLOSSARY_INJECT  ← el WIN principal (+16)
  │      si la query pide DEFINICION y el concepto matchea EXACTO un termino de
  │      fragmentos_definicion, se INYECTA el articulo que lo define en el top-k
  ├─ 7. EXPAND jerarquico
  │
  ▼ top-10 documentos
GENERACION  qwen3:30b-a3b (Ollama, local)
  │  num_ctx=32768 · num_predict=2000 · think=False
  ├─ SELF-CONSISTENCY N=3: genera 3 veces (T=0.7), se queda con la respuesta que
  │  mas respalda el CONSENSO de citas (las que salen en >=2 de 3)     ← 2o WIN
  ├─ strip del bloque <think>  (el modelo razona en el cuerpo; se recorta)
  ├─ verify_citations: toda cita debe existir en el pool -> si no, REINTENTA
  └─ strip_malformed_citations
  ▼
RESPUESTA con citas [Art. N de ID]
```

## A.3 Cómo se mide

```
cita_ok       261/264 = 98.9%   ¿ALGUNA cita pega con el gold?   <- metrica historica
cita_limpia   188/264 = 71%     ademas, >50% de las citas correctas
cita_perfecta 114/264 = 43%     TODAS las citas correctas
precision     0.66              citas correctas / citas unicas
```

⚠️ **`cita_ok` premia rociar.** Por eso se construyó `cita_limpia` (E1,
`scripts/eval_metrics.py`). Sin ella, `think=True` parecía negativo cuando en calidad ganaba.

Set primario: `data/eval/queries_balanced_v2_clean.jsonl` — 264 contestables + 15 `unanswerable`
(piden definiciones que el corpus NO contiene; rechazar es el acierto) + off-domain/off-corpus.
Método: **McNemar pareado**, ambos brazos generados en la misma sesión.

## A.4 Lo que se probó y NO sirvió (no repetir)

```
pool 50->100          0 flips en 279 pares
Qwen3-Reranker-4B     +2 = ruido, 17x mas lento
think=True            -16 golds (aunque sube precision)
hibrido think         -10 golds
2 prompts             flat
top_k 10->5 y ->3     flat (top3 si baja 30% el tiempo)
grafo concepto->art   aristas vacias: 0/45 fallas tenian la arista correcta
```

**Ningún cambio de MODELO convirtió nunca.** Lo que movió: arreglar la medición, los datos y bugs.

---

# PARTE B — Las 7 fases del proyecto

El RAG **no es el proyecto**: es la última fase.

```
E0 DESCUBRIR   que normativa existe, por fuente          ❌ FALTA
E1 ACOTAR      regla de corte + poda                     ❌ FALTA (decision del usuario)
E2 BAJAR       scrapear lo que paso el corte             🟡 BCN si, CNE/SEC/CEN no
E3 VINCULAR    grafo norma->norma                        ✅ HECHO (204 aristas)
E4 MAPEAR      norma -> obligacion -> proceso            ❌ NO EMPEZADO  ← EL FOSO
E5 MONITOREAR  cron + hash + diff + aviso                🟡 infra existe, sin cablear
E6 RESPONDER   el RAG                                    ✅ MADURO (98.9%)
```

## E0 — DESCUBRIR ❌
Cuatro fuentes, cuatro mecanismos:

| fuente | qué aporta | estado |
|---|---|---|
| BCN/LeyChile | leyes, DFL, decretos | ✅ Playwright, 95 bajadas |
| **CNE** | **NTCO**, resoluciones exentas | ❌ **sin crawler — lo más operativo** |
| SEC | instructivos, oficios circulares | ❌ sin crawler |
| CEN | procedimientos internos, IVTE | ❌ sin crawler |

Tres estrategias: por índice/materia · por vinculación (✅ funciona: 125 normas nuevas a
profundidad 1) · por citación (`referencias` 5687 filas, **`destino_norma_id` sin resolver**).

## E1 — ACOTAR ❌
Regla propuesta: entra si **(a)** regula generación/transmisión/distribución/mercado eléctrico,
**o (b)** modifica/deroga a una que ya está dentro. **No entra por ser citada de paso.**

Poda pendiente: **14 normas ajenas** (tránsito, transporte público, obras públicas, procesal
penal, insolvencia). Evidencia de que contaminan: las 2 normas más modificadas del corpus son
**Ley de Tránsito (48)** y **Código Procesal Penal (47)**.

## E2 — BAJAR 🟡
BCN funciona (Playwright + stealth, ~15 s/norma). Faltan crawlers CNE/SEC/CEN.
⚠️ `obtxml` de BCN da 429 de cuota — solo sirve el navegador headless.

## E3 — VINCULAR ✅
`norma_vinculacion`: 204 aristas, 172 orígenes, 25 destinos.
```
DEROGADAS   0    ninguna de las 95 lo esta -> el riesgo de citar derogado era teorico
modificadas 25   <- el riesgo REAL: tu texto puede ser version vieja
```

## E4 — MAPEAR ❌ (el foso)
Ligar norma/artículo → obligación → proceso/plazo/cálculo de la subgerencia.
Ejemplo: *arts. 3-27 y 3-29 de la NTCO fijan el plazo del Informe de Valorización de
Transferencias Económicas.*

Un RAG genérico responde *"¿qué dice la norma X?"*.
Este debería responder **"¿qué se rompe en mi proceso si cambia la norma X?"**.
**Nadie fuera del CEN puede construir esto** — es lo único no copiable.

## E5 — MONITOREAR 🟡
Piezas que YA existen: `content_hash` por norma, `versiones`, `descargas_estado`.
Falta el bucle: `cron → re-scrape incremental → diff (hash + vinculaciones) → tabla de eventos → aviso`.

## E6 — RESPONDER ✅
Ver PARTE A. Cerrado salvo: `gen2_n5` (corriendo), D4 (ambigüedad), G9 (gate GraphRAG).

---

# PARTE C — Qué falta, en orden

| # | qué | fase | por qué ahora |
|---|---|---|---|
| 1 | **Definir la frontera** (decisión del usuario) | E1 | sin esto no se automatiza nada |
| 2 | **Crawler CNE** (NTCO + resoluciones exentas) | E0/E2 | sin la NTCO el corpus no cubre la operación diaria |
| 3 | **Podar las 14 normas ajenas** | E1 | barato, quita ruido medido |
| 4 | **Resolver `referencias.destino_norma_id`** | E0 | habilita descubrimiento por citación |
| 5 | **Re-bajar las 25 normas modificadas** | E2 | el texto guardado puede ser versión vieja |
| 6 | **Monitor de cambios** | E5 | es lo que se pidió; toda la infra existe |
| 7 | **Piloto E4** con UN proceso (IVTE) | E4 | valida el foso antes de escalarlo |
| 8 | Token GitHub (21 commits locales) | — | bloqueado por el usuario |

**Menor prioridad (E6, rendimiento decreciente):** D4 ambigüedad · G9 eval multi-hop · escala
(R1 metadata filtering, C1 Contextual Retrieval, recalibrar gate off-topic).

---

# PARTE D — Riesgos medidos

1. **BCN lento y frágil.** ~15 s/norma vía navegador; depende de selectores del DOM → si BCN
   cambia, se rompe **en silencio**. Necesita test de humo ruidoso.
2. **GPU: Xid 79 dos veces** bajo carga sostenida (2h30 y 4h) → exige reinicio del nodo.
   Mitigación sugerida y no aplicada: `sudo nvidia-smi -pl 250`.
3. **Gate off-topic calibrado solo para energía** → al ampliar materias hay que recalibrarlo.
4. **`prompt_doc_char_budget` ya roza el límite** (prompts de 50k chars). Más corpus ⇒ re-medir.
5. **Latencia:** self-consistency N=3 cuesta 3× (20.8 → 61.4 s por respuesta).
