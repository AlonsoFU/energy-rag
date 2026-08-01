# Investigación: mejoras a la arquitectura RAG (2026-07-31)

Deep-research (5 ángulos, 22 fuentes, 25 claims verificados adversarialmente 3-votos,
20 confirmados / 5 refutados). Fuente: workflow `deep-research` sobre `docs/handoff-2026-07-31.md`.
Cada mejora marca factibilidad en **RTX 3090 24GB VRAM + 14GB RAM, offline**.

## Veredicto de fondo

El stack actual (BM25+denso → RRF → cross-encoder rerank → gen LLM local) **ES el
baseline recomendado 2024-2026 para RAG legal/estatutario**. Benchmarks independientes lo
confirman (two-stage híbrido Recall@5 0.816 vs single-stage RRF 0.695 / BM25 0.644 / denso
0.587). → **No cambiar el pipeline. Las ganancias vienen de DATOS/ESTRUCTURA, no de swaps de
modelo.** (3-0)

Refutados en verificación (NO asumir): "reranker es el componente más impactante (+12.1pp)"
(0-3); "rerank mejora significativamente RAG legal" (0-3); "la mayoría de las alucinaciones
vienen del retrieval, no del razonamiento" (0-3). → El reranker/retrieval solo NO es la palanca
decisiva. Coherente con lo ya medido acá (coloquial subió por retrieval, dev por generación).

---

## Mejoras priorizadas (todas CABEN en el 3090 + 14GB)

### 1. Rerank sobre 50-100 candidatos, no top-10 — FIX GRATIS, hacer primero
- **Qué:** el reranker solo reordena, nunca recupera lo que no está en su pool. Hoy se rerankea
  a top-10 → el techo de recall queda en el recall@10 de la fusión. Alimentar BGE con 50-100
  candidatos sube el techo para la definición enterrada del art 225 y los residuos coloquiales
  (torres vida útil, planta solar) que la fusión rankea bajo 10. (3-0)
- **GPU:** ✅ trivial en 3090 (batch cross-encoder más grande, BGE ya en GPU 0.13s/32pares).
- **Riesgo:** "siempre ayuda" es demasiado fuerte — pools enormes meten ruido a rerankers
  débiles, pero BGE-reranker-v2-m3 es fuerte y 50-100 es estándar. Medir dev+holdout, no-regresión.
- **Costo:** ~1 parámetro (`retrieval_pool_depth` al rerank). Flag-gated.

### 2. STARA — aumentar cada artículo con sus definiciones + referencias + padre antes de indexar
- **Qué:** Stanford RegLab (ICAIL 2025). Parsear preservando jerarquía y enriquecer cada
  disposición con sus definiciones enlazadas, cross-references y artículo padre ANTES de
  indexar. Ataca DIRECTO el problema art 225: en vez de un chunk denso, la definición específica
  queda co-localizada con los términos de la query. LaborBench 83% (92% corregido). (3-0)
- **GPU:** ✅ puro preprocesamiento/indexado en CPU + LLM local. Cero VRAM extra. Offline.
- **Caveat:** benchmark único (US labor law); la técnica estructural generaliza, el número no.
- **Es el template más fuerte para los frentes abiertos** (glosario denso + residuo coloquial).
  Conecta con la vieja idea "1 def = 1 fragmento".

### 3. "1 definición = 1 fragmento" + parent-document retrieval para el art 225
- **Qué:** partir el artículo-glosario multi-definición en fragmentos de una def cada uno
  (recupera fino), pero devolver el artículo padre completo al generador (contexto). Es la
  versión SIMPLE y probada de la granularidad dinámica. (3-0, deriva de STARA + MoGG)
- **GPU:** ✅ preprocesamiento local, sin VRAM.
- **Preferir esto ANTES que** Mix-of-Granularity (MoG): MoG usa un router entrenado (MoE) que
  requiere DATOS ETIQUETADOS y entrenamiento → costo/riesgo real para setup offline single-GPU.
  MoGG (grafo) junta snippets no-contiguos, útil pero más complejo. Empezar por lo simple.

### 4. Summary-Augmented Chunking (SAC) — prepend resumen de norma a cada chunk
- **Qué:** el modo de falla dominante en RAG legal es **cross-document mismatch (DRM)**: traer
  el chunk de la NORMA equivocada porque comparte fraseo legal boilerplate (>95% DRM en corpus
  legales lexicamente similares). Prepender 1 resumen de ~150 char (LLM) por documento a cada
  chunk antes de embeder reduce DRM (~95%→~50%) y mejora precisión Y recall. (3-0)
- **GPU:** ✅ 1 pasada de resumen qwen3:30b por norma (~78), trivial.
- **Caveat GRANDE:** "reduce a la mitad en TODOS los datasets" fue REFUTADO (1-2). El efecto es
  fuerte en corpus muy similares y depende del embedder. Con solo ~78 normas (vs 362 de
  ContractNLI) la presión DRM puede ser MENOR → **medir si mueve cita_ok o solo agrega una
  pasada de resumen.** Es open question, no adopción directa.

### 5. Step-back query rewriting — complemento liviano al alias-map coloquial
- **Qué:** reescribir la query a una versión más abstracta/general. En QA legal italiano step-back
  ganó a multi-query y decomposición en ambos sub-dominios. (3-0)
- **GPU:** ✅ 1 reescritura qwen3:30b local, casi cero costo.
- **Clave:** valida el diseño actual — el **alias-map determinista (vocabulario controlado) es la
  decisión CORRECTA para precisión de cita.** Agregar step-back como complemento liviano, NO
  reemplazar el alias-map.
- **Caveat:** evidencia single-study, una jurisdicción, eval con LLM-judge. Medir en holdout.

---

## NO hacer / sobre-ingeniería (probado que puede dañar cita_ok)

- **HyDE y multi-query:** subrendieron en retrieval preciso/numérico — los documentos
  hipotéticos generados meten cifras alucinadas que desvían el embedding. Peligro directo para
  cita_ok (donde citar el [Art N de NORMA] exacto ES la métrica). **Evitar HyDE.** (3-0)
- **DMQR-RAG (4 reescrituras diversas):** su rama pseudo-answer ES HyDE (riesgosa). Keyword +
  core-content sí alinean con cita. Usar como menú para enriquecer el union del alias-map, NO
  fan-out completo salvo que mueva holdout. (3-0)
- **Mix-of-Granularity (router entrenado):** requiere datos etiquetados + entrenamiento. Costo
  real offline. Preferir #3 simple primero.

---

## Multi-vector / ColBERT — el ÚNICO punto donde el hardware/stack limita

- **Qué:** ColBERT/ColPali = late-interaction (1 vector por token, matching MaxSim). Granularidad
  token-level que PODRÍA sacar la definición enterrada del art 225. (3-0)
- **GPU:** ✅ **como RERANKER** sobre 100-500 candidatos cabe en 3090 (set chico), podría
  complementar/reemplazar BGE. (3-0)
- **⚠️ LÍMITE DURO DEL STACK (no del hardware):** pgvector **NO tiene tipo multi-vector nativo ni
  MaxSim indexado**. Los vectores por-token se guardan como `vector[]` y MaxSim se escribe como
  función SQL a mano → solo **fuerza bruta exacta**. (2-1 / 3-0)
  - → ColBERT es factible para **rerank de un pool acotado**, NO para retrieval de primera etapa a
    escala en pgvector puro.
  - Para late-interaction indexado a escala: se necesita **extensión aparte (VectorChord
    turbohybrid)** o esquema 1-token-por-fila. Es complejidad operacional — open question si vale.
- **A escala (cientos de miles de art):** mantener HNSW single-vector (el qwen3 MRL-1024) como
  primera etapa + pre-filtro por metadata (norma/jerarquía), y confinar late-interaction al
  rerank. **La restricción es de pgvector, NO del 3090.**

---

## Escalabilidad pgvector (cuello = 14GB RAM, no VRAM)

- HNSW debe residir ENTERO en RAM para su latencia; ~20-25 KB/vector real → la RAM debe escalar
  con el índice. Con ~3000 art hoy no hay problema; a cientos de miles, vigilar los 14GB.
- pgvector 0.8.0: iterative index scans arreglan el filtrado por metadata (antes devolvía menos
  resultados que k). Útil para pre-filtro por norma.
- Límite dim: HNSW/IVFFlat tope 2000-dim (halfvec 4000, DiskANN 16000). MRL-1024 actual: no-issue,
  pero limita futuros embedders de mayor dim.
- pgvector+pgvectorscale escaló a 50M vectores 11.4× throughput vs Qdrant single-node → pgvector
  aguanta; el límite práctico es la RAM del host.

---

## Orden sugerido (mínimo esfuerzo → máximo, todo flag-gated + medir dev/holdout)

1. **Rerank 50-100 candidatos** (#1) — 1 parámetro, gratis, sube techo de recall. HACER YA.
2. **1 def = 1 fragmento + parent-doc** para art 225 (#3) — preprocesamiento, ataca 4/8 fallas dev.
3. **STARA** aumentación estructural (#2) — si #3 no cierra el cluster art 225.
4. **Step-back rewriting** (#5) — para residuos coloquiales, complemento del alias-map.
5. **SAC** (#4) — solo si DRM se confirma como causa real (medir; corpus chico puede no necesitarlo).
6. **ColBERT rerank** — experimental, solo si #1-#3 no bastan; ojo límite pgvector.

## Open questions (del research)
- ¿"1 def = 1 fragmento" + parent-doc resuelve el art 225 solo, o hace falta ColBERT rerank?
  ¿Cuál mueve más cita_ok en holdout?
- ¿SAC ayuda o solo agrega latencia en corpus de ~78 normas (menos presión DRM que 362)?
- ¿Los residuos coloquiales (torres vida útil, planta solar) necesitan expandir el alias-map
  (curación manual) o step-back cierra sin tocar el glosario?
- ¿Vale VectorChord para late-interaction indexado, o confinar ColBERT a rerank de pool acotado?

## Caveats de la investigación
- Fuentes clave son de otras jurisdicciones (STARA=US labor, step-back=Italia, benchmark
  text+table=finanzas). Las TÉCNICAS estructurales generalizan; los NÚMEROS no → validar cada una
  en dev+holdout con disciplina estándar-vs-hipótesis, no-regresión, antes de adoptar.
- Varias fuentes primarias tienen arXiv IDs 2026 (STARA 2603.03300, 2604.01733) cerca del cutoff
  → tratar números exactos como recientes-pero-móviles.

## Con la 3090 vs. con mejor hardware (¿qué desbloquea más fierro?)

**Conclusión honesta: para ESTE problema, más GPU aporta poco. Las ganancias son
estructurales/de datos y TODAS caben en la 3090.** El cuello real es RAM del host, no VRAM.

| Técnica | Con RTX 3090 24GB + 14GB RAM (hoy) | Con mejor hardware |
|---|---|---|
| M1 rerank 50-100 | ✅ completo | = (no cambia) |
| M2/M3 STARA + 1def=1frag | ✅ completo (CPU+LLM) | = (no cambia) |
| M4 step-back / M5 SAC | ✅ completo | = (no cambia) |
| LLM gen | ✅ 30b-a3b (MoE) y hasta 32b denso caben | 48GB → 70B denso; **no medido que mejore cita_ok** (bake-off ya coronó 30b-a3b) |
| Embedder | ✅ 4B-1024 (8B cabe pero fue trade-off) | = (8B ya cabe y NO ganó coloquial) |
| Concurrencia | swap embedder↔LLM entre fases (2-phase eval) | 2×24GB o 48GB → todo residente, sin swap → **solo velocidad de eval, no calidad** |
| ColBERT rerank pool acotado | ✅ cabe | = |
| **ColBERT/multi-vector retrieval 1ª etapa a escala** | ❌ | ❌ **igual con más GPU** — límite es pgvector (sin MaxSim indexado), NO el fierro. Se arregla con extensión (VectorChord), no con GPU |
| **HNSW a cientos de miles de art** | ⚠️ límite 14GB RAM (HNSW debe caber en RAM) | ✅ **MÁS RAM del host** (no GPU) es lo único que realmente escala esto |

**Qué SÍ pediría si hubiera presupuesto (por prioridad):**
1. **Más RAM del host** (no GPU): 32-64GB → HNSW de cientos de miles de art residente. Es el único
   cuello real de ESCALA. (14GB → hoy alcanza para ~3000 art, no para toda la ley chilena.)
2. **Extensión pgvector (VectorChord)** — para late-interaction indexado a escala. Es software, no
   hardware.
3. GPU mayor: al final de la lista. 30b-a3b ya ganó el bake-off; 70B denso NO está medido que mejore
   cita_ok. Más VRAM solo evita el swap entre fases → acelera evals, no sube calidad.

**Traducción:** el fierro NO es el límite de calidad hoy. Con la 3090 se puede ejecutar TODO el
backlog M1-M6. El límite futuro es RAM (escala) y una extensión de pgvector (multi-vector), ninguno
se resuelve comprando una GPU más grande.

## Tus modelos vs. frontera (deep-research verificado 3-votos, 2026-08-01)

**Números citados de benchmarks públicos. Caveat: NO medido en la eval propia (101q) ni en
retrieval legal-español chileno — es extrapolación.** Restricción: sin API paga → gap open-vs-
frontera-REAL en extracción grounded NO tiene medición directa publicada.

| componente | actual (3090) | vs frontera | veredicto |
|---|---|---|---|
| **embedder** | qwen3-embedding-4B MRL-1024 | MTEB multilingüe: Qwen3-emb-8B **70.58/70.88 (#1)**, 4B **69.45/69.60** > Gemini 68.37/67.71 > Cohere-v3 61.12/59.16 > OpenAI text-emb-3-large 58.93/59.27 | **TU embedder YA SUPERA a los frontera cerrados.** ⚠️ falta Voyage-law-2 (legal-específico) en el set |
| **reranker** | bge-reranker-v2-m3 | MMTEB-R: bge-v2-m3 **58.36** vs Qwen3-Reranker-4B **72.74** / 8B **72.94** (gap **~14 pts**) | **TU RERANKER es el eslabón débil.** Upgrade OPEN disponible, cabe en 3090 → cola activa (RK1) |
| **gen LLM** | qwen3:30b-a3b (30B/3B) | legal-QA: Qwen3-A3B **46.5%** ≈ GPT-4o-mini **47.2%** (p=0.19). Cita closed-book: Claude Sonnet 4.5 solo **6.80/100**, Llama-70B **3.82** ≈ 8B **1.47** | gap RAZONAMIENTO grande, gap EXTRACCIÓN chico. Tamaño/frontera NO da cita; el retrieval sí |

**Conclusiones verificadas (3-0):**
1. **Retrieval > generador.** Múltiples estudios (2510.06999 NLLP'25; 2605.14503 ACM FSE'26 peer-
   reviewed, 7 retrievers × 6 generadores): "el retriever, sobre todo el algoritmo de recuperación,
   influye más que la elección del generador". El fallo dominante (Document-Level Retrieval
   Mismatch) es de recuperación, no de generación.
2. **Escalar el LLM NO da cita.** Closed-book: ningún frontera pasa 7/100; Llama 8B→70B (9× más
   grande) apenas sube. La cita correcta viene del retrieval, no del tamaño ni del conocimiento
   paramétrico.
3. **Tu embedder ya es frontera-o-superior** (Qwen3-emb). Truncar 2560→1024 (~60% reducción) está
   en zona segura (paper "To MRL or not to MRL" 2605.16608 incluye Qwen3-4B explícito: sin
   diferencia MRL a ningún nivel para modelos ~4B).
4. **Frontera cerrada en gen no mueve la aguja** para extracción de cita con retrieval fijo →
   rompería "sin API paga" para ganancia marginal. Solo como 1 diagnóstico de techo, nunca producción.

**Único hallazgo accionable HOY (open, cabe en 3090, NO frontera):** upgrade reranker
**bge-reranker-v2-m3 → Qwen3-Reranker-4B/8B** (gap ~14 pts en benchmark). Es el cambio de mayor
retorno teórico sin probar en el sistema → **RK1 en el backlog.**

**Caveats duros:** (1) números de embedder/reranker son self-report Qwen sobre benchmarks públicos
(MTEB/MMTEB), NO legal-español chileno; (2) falta Voyage-law-2, el frontera legal-específico —
única brecha donde la superioridad open NO está probada; (3) GPT-4o-mini NO es frontera real (es el
barato de OpenAI) → el empate no dice nada de GPT-5/Opus/Gemini; (4) LegalCiteBench/ECtHR miden
recuperación/predicción closed-book, más duras que extraer un N° de artículo de contexto YA
recuperado → no leer como que cita_ok grounded es imposible, solo que sin retrieval nada funciona.

**Orden de retorno esperado (teórico) si algún día escalo:**
1. **Estructura/datos + grafo** (M1-M3, G1) — cuello real, gratis en 3090.
2. **RK1 upgrade reranker Qwen3-Reranker** — open, cabe en 3090, gap ~14 pts. Mayor retorno de modelo.
3. **Embedder 8B / full-dim** — cabe en 3090, upside chico (ya eres frontera).
4. **LLM denso 70B+** (>24GB, NO cabe) — upside marginal en cita_ok (research: escalar no da cita).
5. **Frontera cerrada (API)** — rompe "sin API paga", ganancia marginal. Solo diagnóstico.

## Fuentes principales
- STARA (structure-aware statutory RAG): arxiv.org/html/2603.03300
- SAC / DRM legal a escala: aclanthology.org/2025.nllp-1.3.pdf, arxiv.org/html/2510.06999v1
- Two-stage híbrido baseline: arxiv.org/html/2604.01733v1, emergentmind.com/topics/legalbench-rag
- MoG/MoGG granularidad: arxiv.org/pdf/2406.00456
- ColBERT rerank + límite pgvector: qdrant.tech/documentation/fastembed/fastembed-colbert/,
  github.com/pgvector/pgvector/issues/694
- Step-back / query rewriting legal: link.springer.com/chapter/10.1007/978-3-031-96099-4_9
- DMQR-RAG: arxiv.org/abs/2411.13154
- LegalBench-RAG (eval span-level): arxiv.org/abs/2408.10343
