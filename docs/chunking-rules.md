# Chunking — reglas, consideraciones y QA

Doc canónico del chunking del corpus legal. Escrito 2026-07-09 tras la campaña
(sweep 17 estrategias + end-to-end + QA). **Veredicto: producción se queda como está
(`asis`). Ningún re-chunk adoptado.**

---

## 1. El estándar legal-RAG (investigado, no inventado)

Cuatro reglas que la literatura y los sistemas de producción convergen en usar:

| # | regla | qué dice | estado nuestro |
|---|-------|----------|----------------|
| 1 | **section-aware** | partir por la jerarquía propia del documento (artículo/inciso), NO por tamaño fijo | ✓ partimos por artículo. Probamos inciso → **descartado** (ver §4) |
| 2 | **una provisión = un chunk** | no fundir 50 definiciones en un mega-chunk; no partir a mitad de provisión | ~parcial (glosarios siguen fundidos; el split no convirtió) |
| 3 | **context enrichment (header-path)** | anteponer la ruta `[norma > título > art N]` al texto antes de embeber | ✓ `contextual_text` |
| 4 | **cross-ref / late-chunking** | embeber el chunk con el contexto de lo que referencia ("el Coordinador definido en art X") | ✗ **NO PROBADA — única virgen** |

Evidencia externa: un estudio clínico midió chunking por límites lógicos = **87% accuracy
vs 13%** para fixed-size. La regla 1 no es opinión.

Fuentes:
- [LegalBench-RAG (arXiv 2408.10343)](https://arxiv.org/pdf/2408.10343)
- [Towards Reliable Retrieval in RAG for Large Legal Datasets (arXiv 2510.06999)](https://arxiv.org/pdf/2510.06999)
- [CoFE-RAG — eval full-chain incl. chunking (arXiv 2410.12248)](https://arxiv.org/pdf/2410.12248)
- [HOPE — eval automática domain-agnostic de chunking (arXiv 2505.02171)](https://arxiv.org/pdf/2505.02171)
- [Chunking Strategies for Legal & Reference RAG — Edtek](https://edtek.ai/kb/chunking-strategies-legal-reference-documents/)

---

## 2. Reglas de estructura (los regex, antes sueltos en el código)

Viven en `scripts/exp_chunk_sweep.py`. Detectan la estructura que la norma **ya tiene**
(no inventan divisiones — eso es requisito legal-safe).

| símbolo | regex | detecta | ejemplo | límite conocido |
|---|---|---|---|---|
| `_GLOS` | `se\s+entender[áa]\s+por\s*:` | inicio de artículo-glosario | *"...se entenderá por:"* | no cubre glosarios con otra fórmula ("Para efectos de...") |
| `_MARK` | `(?:^\|\n\|;)\s*(?:[a-zñ]{1,2}\|\d{1,2})[.)]\s+` | subdivisión simple | `a. `, `b) `, `1. `, `12) ` | no cubre `1°`, romanos, ordinales, `§` |
| `_MARK2` | `_MARK` + `\d{1,2}[°º]` + `[IVXLC]{1,4}` + `Primero..Décimo` + `§\s*\d` | subdivisión extendida | `1°`, `III.`, `Primero.-`, `§ 4` | falsos positivos con `I.` en siglas |
| `_SENT` | `(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ0-9])` | frontera de oración | corte de fragmentos gigantes | corta en abreviaturas (`art. 5`) |
| `HUGE` | `3000` | umbral de mega-chunk | usado por `ck_inciso_maxsplit` | valor a ojo, no tuneado |

**Trampa descubierta (y corregida):** un chunk de inciso empieza con el marcador `"a. …"`
→ arranca en **minúscula**. Una métrica ingenua de "empieza en minúscula = cortado a mitad
de frase" da **27.9% falso**; quitando el marcador primero (`_LEAD` en `qa_chunking.py`)
el número real es **0.4%**. Medir mal es peor que no medir.

---

## 3. QA de chunking (`scripts/qa_chunking.py`)

Chequeos que el sweep NUNCA hizo. El screen solo mide retrieval; no ve si el chunk está
mutilado. Un chunk puede ser **nítido para buscar** y **basura para responder**.

| métrica | qué mide | señal mala |
|---|---|---|
| **cobertura** | Σ chars(chunks) / chars(artículo) | `<1` = texto perdido · `>1` = redundancia (solape) |
| **perdida_arts** | artículos con cobertura <0.99 | texto realmente perdido |
| **tiny / huge** | chunks <50c / >3000c | huérfanos sin contenido / señal diluida |
| **p10/p50/p90/max** | distribución de tamaños | colas extremas |
| **start_lower%** | empieza en minúscula (tras quitar marcador) | corte a mitad de frase |
| **no_end_punct%** | no termina en `.;:!?)` | corte a mitad de frase |
| **defsCut%** | spans `PADRE: hijo` que NO aparecen íntegros en ningún chunk | cláusula hija separada de su padre |

Del estándar (CoFE-RAG / span-based), pendientes de implementar: `Coverage@k`,
`Redundancy@k`, `MRR@k` sobre spans gold.

Correr: `./venv-gpu/bin/python -m scripts.qa_chunking`

### Resultados QA (2026-07-09, 2978 artículos)
```
chunker           chunks  cobert  perdi   tiny  huge   p10   p50    p90    max startLo%  noEnd% defsCut%
whole               2978   1.000      0     58   262   196   678   2749  41037      0.0    23.4      0.0
glossary            3203   1.000     10     72   254   174   612   2561  41037      0.0    25.3      0.0
inciso              7087   0.999      9    464   145    62   273   1288  11681      0.4    23.0     22.3
inciso_robust       7141   0.999      9    466   142    62   272   1276  11681      0.4    23.0     22.3
inciso_maxsplit     7316   0.999      9    466     0    63   280   1375   2988      0.4    22.4     22.3
slide1000_200       6255   1.161      0    116     0   220   923    992   1000     47.1    59.0      0.0
slide500_100       11080   1.200      0    264     0   178   489    499    500     65.7    74.1      3.7
recursive           9979   0.998      0    236     0   154   408    566   1302      7.1    25.7     29.2
```
Lecturas:
- `no_end_punct ≈ 23%` en **whole** también → es propiedad del **corpus** (artículos sin
  puntuación final), NO patología del chunker. Baseline, no alarma.
- **slide** rompe frases de verdad (`startLo` 47–66%) y **duplica 16–20%** de texto
  (`cobert` 1.16/1.20). Explica su peor coloquial.
- **inciso** NO corta frases (0.4%) pero deja **464 chunks huérfanos** (<50c, 8× más que
  whole) y parte **22.3%** de spans padre:hijo.
- `glossary` pierde texto en 10 artículos (cobert <0.99) — el parser descarta ítems sin `:`.

### Cobertura de estructura (`scripts/exp_chunk_qa.py`, 2978 artículos)
Complementario al anterior: ¿el regex se está perdiendo estructura que la norma SÍ tiene?
```
inciso_1chunk    2442   artículos sin subdivisión detectada (82%) → quedan enteros
big_1chunk        378   artículos >1500c que quedan en 1 chunk (prosa, sin estructura)
alt_markers        29   usan marcadores NO cubiertos por _MARK: § 14 · N° 11 · guion 3 · romano 1
glos_noparse        2   parecen glosario pero no parsean defs
degenerate          0
```
Lectura: la cobertura del regex es **buena** (solo 29/2978 usan marcadores no cubiertos).
Los 378 `big_1chunk` no son un bug: son artículos de **prosa** sin subdivisión legal.
`_MARK2` extiende a `§`/`N°`/romanos/ordinales y recoge esos 29.

---

## 4. Resultados medidos y VEREDICTO

### Sweep de retrieval (screen, vector-only 4b-1024, coloquial 39 + dev 44)
Baseline `asis` (fragmentos actuales) = cx5 **27**, dev5 **28**.
```
estrategia              frags  cx5  dv5  Δcx5  Δdv5
inciso+path              7087   29   38    +2   +10   ← ganador SCREEN
inciso_robust+path       7141   29   38    +2   +10
inciso_maxsplit+path     7316   29   37    +2    +9
inciso+light             7087   28   37    +1    +9
slide500_100+light      11080   25   33    -2    +5
recursive+path           9979   27   31    +0    +3
whole+path               2978   30   26    +3    -2
glossary+light           3203   28   28    +1    +0
asis (baseline)          3907   27   28    +0    +0
```

### End-to-end (cita_ok) — lo único que cuenta
```
inciso:  coloquial -4  ·  dev +2  ·  NET -2   → ESPEJISMO, DESCARTADO (commit 2a76cfb)
```

### Por qué inciso ganó el screen y perdió el end-to-end
El QA lo explica:
```
SCREEN  : el embedder ve trozos chicos y nítidos → el gold sube de rank (+10 dev)
E2E     : el LLM recibe 464 chunks huérfanos + 22.3% de cláusulas sin su padre
          → no puede citar bien → coloquial -4
```
Ejemplo real del daño (art 1199483/45):
```
original :  "1. En el artículo 1: a) Reemplázase en el inciso primero la expresión '2024' por..."
inciso   →  chunk A: "1. En el artículo 1:"                    ← contexto sin acción
            chunk B: "a) Reemplázase en el inciso primero..."  ← acción sin saber QUÉ artículo
```
El chunk B es un **distractor puro**: recuperable, ilegible, incitable. La regla 3
(header-path) le pone `[norma > art 45]` pero **no le devuelve el padre** `"En el artículo 1:"`.

**Moraleja:** *granularidad fina sube el recall y baja la citabilidad.* Un chunk debe ser
**autocontenido**, no solo semánticamente puro. Es la regla 2 bien entendida: la "provisión"
no es la subdivisión sintáctica, es la **unidad que se sostiene sola**.

---

## 5. Consideraciones / trade-offs

| eje | tensión |
|---|---|
| **granularidad vs distractores** | + fino → + recall (screen) → − citabilidad (e2e). El punto dulce NO es el más fino. |
| **n_chunks vs costo** | inciso = 7087 vs 3907 (1.8×) → 1.8× storage, embed y latencia de rerank. |
| **autocontención vs pureza semántica** | un chunk hijo es semánticamente puro pero no se sostiene solo. |
| **screen vs e2e** | el screen MIENTE. Ver §6. |
| **legal-safe** | solo partir por divisiones que la norma ya define. Nunca inventar. |

---

## 6. Lección: el screen MIENTE (3ª confirmación)

| # | experimento | screen | end-to-end |
|---|---|---|---|
| 1 | embedder 8b | gold∈top5 **+2** | cita_ok **−1** |
| 2 | ensemble retrieval | gold∈top10 **+8** | cita_ok **−3** |
| 3 | **chunking inciso** | gold∈top5 **+10 dev** | cita_ok **NET −2** |

**Regla dura del proyecto: ningún candidato se adopta por screen. Se confirma end-to-end
(cita_ok) o no cuenta.** Subir el recall del pool sin cuidar la calidad del chunk
solo cambia *qué* distractor cita el LLM.

---

## 7. Estado y próximo paso

- **Producción: `asis` (sin cambios).** Chunking cerrado: sweep ✓, e2e ✓, QA ✓.
- **Regla 4 (cross-ref / late-chunking) = única virgen.** Es además la que atacaría
  justo la patología encontrada (chunk sin su contexto padre/referenciado).
- Deuda menor: `glossary` pierde texto en 10 artículos; `_MARK2` tiene falsos positivos
  con romanos; `HUGE=3000` sin tunear; faltan `Coverage@k`/`Redundancy@k`/`MRR@k`.

Scripts: `scripts/exp_chunk_sweep.py` (sweep) · `scripts/qa_chunking.py` (QA).
Datos: `data/eval/results/chunk_sweep/result.json`.
