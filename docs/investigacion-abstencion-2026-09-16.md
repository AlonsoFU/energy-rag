# Investigacion: abstencion, confianza y guardarrailes (2026-09-16)

Deep research sobre fuentes primarias (papers leidos, no snippets) para responder:
**¿como hacer que el sistema diga "no se" en vez de inventar, y cual es el estandar?**

Resumen ejecutivo: **el estandar NO esta converged.** Hay tres familias de mecanismo
(juez LLM, clasificador entrenado, umbral sobre embeddings) sin dominante. Lo unico
convergente: descomponer en afirmaciones/spans y tratar "citado pero no soportado" como
una clase de falla propia, distinta de "sin cita".

Tres errores del plan que yo mismo habia propuesto (corregidos abajo): el metodo de
construccion de negativos era incorrecto, faltaba por completo el modo de falla mas grave
(contexto ENGANOSO), y el orden ponia el juez antes que las senales gratis.

---

## 1. Lo que mide el estandar legal (Stanford RegLab / JELS 2025)

Magesh, Surani, Dahl, Suzgun, Manning, Ho — *Journal of Empirical Legal Studies* 2025.
202 consultas, puntuadas por expertos.

Taxonomia (2 ejes, Tabla 1):
- **Correctness**: Correct (incluye parcial-pero-incompleta) / Incorrect / Refusal.
- **Groundedness** (solo sobre las Correct): **Grounded** (la fuente citada respalda) /
  **Misgrounded** (cita una fuente que NO respalda o no aplica) / **Ungrounded** (sin cita).
- **Hallucination := Incorrect OR Misgrounded.** Accurate := Correct AND Grounded.

| herramienta | accurate | hallucinated | incomplete |
|---|---|---|---|
| Lexis+ AI | 65% | ~17% | 18% |
| Westlaw AI-Assisted Research | ~41-42% | 33% | 25% |
| Ask Practical Law AI | 19% | — | 62% |
| GPT-4 a libro cerrado | peor que las tres | — | — |

**Esto aplica DIRECTO a nuestro bug medido.** Las 29/103 de dev (cita textual real, pero de
articulo distinto al gold) son exactamente la categoria **misgrounded**, que el paper señala
como *mas peligrosa que la fabricacion abierta* porque es mas sutil de detectar.

Recomendacion del paper: hace falta benchmarking independiente de terceros (analogia con
NIST FRVT); los autobenchmarks de proveedor son "far from adequate".

**ADOPTAR:** la matriz Correct x Grounded como esquema de etiquetado manual de nuestro eval.

---

## 2. Senal de suficiencia de contexto (Joren et al., ICLR 2025, arXiv 2411.06037)

Definicion: (Q,C) es *suficiente* si existe una respuesta **plausible** derivable de C. No
requiere ground truth ni que la respuesta sea correcta.

Autorater: Gemini 1.5 Pro 1-shot, **Acc 0.930 / F1 0.935** contra 115 instancias etiquetadas
por humanos. Alternativa barata usada en el paper: FLAMe (PaLM 24B afinado), Acc 0.878.
TRUE-NLI (T5-11B, necesita GT): 0.826. Heuristica "contiene el GT": 0.809.

Generacion selectiva: **no se usa la suficiencia sola.** Regresion logistica de 2 variables
(etiqueta binaria de suficiencia + autoconfianza), 100 iteraciones de busqueda aleatoria de
hiperparametros. Ganancia **2-10 puntos a igual cobertura**; >10 pts para Gemma 27B en
HotpotQA; **cero ganancia en Musique** (accuracy base 18.4% -> el coeficiente de suficiencia
colapso a 0).

Limitaciones medidas (importantes):
- Los LLM responden **correcto 35-62% de las veces aun con contexto insuficiente** ->
  "abstenerse si insuficiente" a secas BOTA respuestas correctas.
- Alucinan mas de lo que se abstienen **incluso con contexto suficiente**.
- Al agregar contexto RAG baja la abstencion y SUBE la alucinacion (Claude 84.1%->52%,
  Gemini 100%->18.6%).

Costo local: 1 llamada extra de LLM por query. **No existe numero publicado de que precision
da este autorater con un modelo abierto de 7-30B** -> habria que medirlo contra un set
etiquetado a mano en español.

Desajuste con nuestro pipeline: su "suficiencia" = plausibilidad de respuesta libre, no
extractabilidad de una cita textual. No mapea 1:1 a quote-only; habria que redefinirla.

---

## 3. CRAG (arXiv 2401.15884) — el evaluador NO es prompt-only

Evaluador = **T5-large (0.77B) AFINADO** sobre ~12.6k ejemplos de PopQA, luego transferido
zero-shot. Comparacion del propio paper: ChatGPT zero-shot como evaluador **58.0%** vs
T5-large afinado **84.3%**. El paper declara que eliminar el evaluador externo afinado es
trabajo futuro, o sea hoy es requisito.

Umbrales (rango ~[-1,1], superior/inferior): PopQA (0.59, -0.99); PubHealth y ARC-Challenge
(0.5, -0.91); Biography (0.95, -0.91). Arriba->Correct, abajo->Incorrect, medio->Ambiguous.

Ganancias con LLaMA2-7b vs RAG plano: PopQA 54.9 vs 50.5; PubHealth 59.5 vs 48.9;
ARC-Challenge 53.7 vs 43.4; Biography FactScore 47.7 vs 44.9.

**Atajo para nosotros:** en vez de entrenar un evaluador, reutilizar el score del
cross-encoder BGE que YA se calcula y ajustarle umbrales estilo CRAG. Costo extra cero.
Caveat: los umbrales del paper son especificos de dataset, hay que reajustarlos.

---

## 4. Senales de confianza baratas (evidencia primaria)

| senal | discriminacion | dataset/modelo | fuente |
|---|---|---|---|
| Entropia semantica | **AUROC 0.828 / 0.767** | TriviaQA / CoQA, OPT-30B | 2302.09664 |
| Consistencia (Self-Random, M=5) | AUROC 73.0 prom (92.7 en GSM8K), ECE 18.7 | GPT-3.5, 8 datasets | 2306.13063 |
| Hibrido consistencia+confianza | AUROC 74.5, ECE 14.8 | idem | 2306.13063 |
| Confianza verbalizada | **AUROC 51.3-62.7**, ECE 18-52 | 5 LLM x 8 datasets | 2306.13063 |
| Logprob de secuencia | ECE 0.14-0.45 (peor calibrado) | ChatGPT/GPT-4 | 2305.14975 |
| Score de reranker | sin AUROC primario hallado | — | **NO VERIFICADO** |
| Juez LLM extra | ningun paper lo muestra ganando | — | evidencia ausente |

Entropia semantica, metodo exacto: muestrear M respuestas, agrupar por **implicacion
bidireccional** con DeBERTa-large-MNLI (92.7% de acuerdo con humanos en TriviaQA, 95.5% en
CoQA), entropia sobre los grupos. Kuhn et al. usaron **10 muestras** ("mas de 10 no mejora
significativamente"); los autores del paper de Nature dicen que **5 basta**.
**Nuestro self_consistency_n=3 esta POR DEBAJO de lo probado** — punto barato razonable, no
optimo demostrado.

Caveat en contra de la propia propuesta: el acuerdo entre muestras tambien es predictor
debil. En 2607.08065, respuestas de GPT-4.1 con acuerdo >=0.8 estaban equivocadas el **48%**
de las veces en GPQA (rho: consistencia 0.31 > verbalizada 0.21 > P(true) 0.19).

Conformal (Angelopoulos & Bates, 2107.07511), tabla de tamaño de calibracion para alpha=0.1,
delta=0.1: eps=0.1 -> n=22; **eps=0.05 -> n=102**; eps=0.01 -> n=2491. Mohri & Hashimoto
(2402.10978) usaron 50 etiquetados por dataset y lo consideran viable.
-> **dev=114 alcanza para alpha=0.1.** Para alpha=0.05 usar el set balanceado de 339.

Ajuste de umbral (estandar): curva **riesgo-cobertura** en dev (ordenar por score, barrer
umbral, riesgo = errores/respondidas, cobertura = respondidas/total), fijar el umbral al
riesgo objetivo, y **validar ese mismo umbral fijo en held-out sin reajustar**. Reportar
ambas curvas lado a lado para exponer overfit.

---

## 5. Construccion del set sin respuesta — MI DISENO ERA INCORRECTO

Yo habia propuesto **quitar la norma gold del indice**. Ninguno de los 4 papers primarios lo
usa, y CRUMQs (2510.11956) lo **rechaza explicitamente**.

Lo que se hace (UAEval4RAG 2412.12300, RGB 2309.01431, CRUMQs, SQuAD2.0 1806.03822):
1. Sacar negativos de contenido que **genuinamente nunca estuvo** en el corpus (temas
   adyacentes, documentos fuera de la base).
2. **Verificar empiricamente** la falta de respuesta: correr el retriever real, top-10, y que
   un juez confirme que ningun chunk responde. Borrar NO garantiza que quede sin respuesta.
3. Deduplicar por similitud de embedding contra corpus y queries existentes.

Evidencia de por que importa: en SQuAD2.0 los negativos automaticos por supervision distante
dan **79.4 F1** vs **65.1 F1** de los escritos a mano — el set facil es explotable por
solapamiento de palabras y hace parecer mejor al sistema.

Metricas (2608.22228 / GRAB-RAG):
- `HwSA = (1/|Sc|) * suma 1[respondio]` sobre el set que debia abstenerse (= 1 - tasa de
  rechazo negativo).
- `FAC  = (1/|C|)  * suma 1[se abstuvo]` sobre el set con respuesta (= rechazo indebido).
- UAEval4RAG: joint `s = w1*Correctness + w2*AcceptableRatio`, por defecto w1=0.7, w2=0.3
  (los autores dicen explicitamente que no es universal).
- SQuAD2.0: abstenerse en un negativo puntua 1; cualquier otra respuesta, 0.

Tamaños observados: UAEval4RAG 600 sin respuesta vs 500 con respuesta; RGB 600 base;
CRUMQs 3048 con Holm-Bonferroni p<0.05. **Nuestros 15 marcados unanswerable son muy pocos:
el IC95 de una proporcion con n=15 es ~±25 puntos.**

---

## 6. EL HUECO GRANDE: contexto ENGANOSO (2608.22228)

Distingue **falta** de contexto (Q0: solo negativos duros) de contexto **enganoso** (QC: un
pasaje con la entidad de la respuesta cambiada por otra plausible, entre negativos duros).

| condicion | responde cuando DEBIA abstenerse |
|---|---|
| falta de contexto (Q0) | **0-3%** |
| contexto enganoso (QC) | **13.6% - 74.3%** (Llama/NQ: 0% -> 74.3%) |

- **59.6%** de las respuestas equivocadas repiten literal la entidad plantada; solo **4.3%**
  se autocorrigen.
- Conclusion textual: *"Prompt-based abstention asks whether context is sufficient, not
  whether it is correct."* Un texto fluido, del tema y equivocado pasa el chequeo igual.
- Mitigacion probada (verificador NLI/DeBERTa): baja HwSA a ~14% pero **sube el rechazo
  indebido a ~31%**. No es gratis. Y sigue fallando cuando la memoria parametrica coincide
  con el pasaje enganoso.

**Este modo de falla es 5 a 70 veces peor que la falta de contexto y hoy no tenemos NI UNA
prueba de el.** Es ademas el vecino conceptual de nuestras 29/103 misgrounded.

---

## 7. Herramientas de guardarrail: viabilidad offline

| herramienta | mecanismo | offline | tamaño | precision reportada | español |
|---|---|---|---|---|---|
| Vectara HHEM-2.1-Open | flan-t5-base afinado, premisa/hipotesis -> 0-1 | si | 0.1B, <600MB | 74.28% bal.acc en RAGTruth-QA (numero del propio proveedor) | no (open = solo ingles) |
| AlignScore (ACL 2023) | RoBERTa entrenado en 4.7M ejemplos NLI/QA | si | 125M/355M | iguala o supera GPT-4 en TRUE | sin checkpoint español |
| MiniCheck (EMNLP 2024) | doc+oracion -> 0/1 | si | FT5 770M | iguala GPT-4 en LLM-AggreFact, ~400x mas barato | sin variante español |
| RAGAS faithfulness | LLM descompone en claims y verifica | si con LLM local | cualquiera | **sin numero oficial** | depende del juez |
| NeMo self-check-facts | prompt al mismo LLM configurado | si | cualquiera | **ninguna publicada**; NVIDIA dice que depende del LLM | no probado |
| Guardrails AI provenance | juez LLM o coseno vs chunks | si | — | **ninguna publicada** (solo blog) | no probado |
| Azure groundedness | clasificador hospedado | **NO, API hospedada** | no revelado | no publicada | **solo ingles** |

**Ninguna ataca nuestro bug.** Todas verifican que el texto este respaldado — y nuestro texto
SI esta respaldado, solo que por el articulo equivocado. Nuestras 29/103 son un problema de
**recuperacion/atribucion**, no de fidelidad de generacion.

Caveat sobre la recomendacion "verificacion deterministica por substring": **ya la tenemos**
(quote-only verifica la cita como substring del articulo recuperado), y la variante de
unicidad de procedencia es exactamente el experimento **#77, ya medido: efecto cero**
(dev cita_limpia 80->79, held-out 21/21 -> 21/21). No repetir.

---

## 8. Estado de nuestras senales (medido 2026-09-16)

Ver `docs/plan-operacion.md`, seccion DIAGNOSTICO 2026-09-16. Resumen: `n_cits` y `n_uniq`
casi no separan acierto de error; `precision` separa bien pero **se calcula contra el gold**,
no existe al responder. `_bge_max` y el acuerdo de autoconsistencia **no se persisten**.

---

## 9. Plan corregido

**Fase 0a — instrumentar (bloqueante).** Persistir por query: `_bge_max`, margen entre top1 y
top2 del reranker, acuerdo entre las muestras de autoconsistencia, n de citas verificadas.
Sin esto no hay umbral calibrable. Criterio: los campos aparecen en `result.json` y no cambia
ninguna metrica (corrida identica a `qonly2_dev`).

**Fase 0b — negativos duros, 60-90.** Receta out-of-database de UAEval4RAG: normas electricas
chilenas reales FUERA de las 95 del corpus, preguntas en el mismo registro que las 279
in_domain, verificacion empirica con el retriever real top-10 + juez, dedup por similitud
>=0.95. NO por remocion del gold.

**Fase 0c — brazo de contexto enganoso.** Cambiar el numero de articulo/norma citado por otro
plausible dentro del pasaje, mezclado con negativos duros. Mide el modo de falla grave que
hoy no se prueba.

Metricas de las tres: `HwSA` y `FAC` **siempre juntas**, nunca una sola; McNemar pareado;
etiquetado manual de una muestra con la matriz Correct x Grounded de JELS.

**Fase 1 — abstencion con senales gratis.** Curva riesgo-cobertura en dev, umbral fijo,
validacion en held-out sin reajuste. Candidatos: entropia semantica sobre las muestras de
autoconsistencia (requiere subir n de 3 a >=5 y un modelo NLI **en español** — pendiente
verificar cual; DeBERTa-large-MNLI es ingles) y margen BGE con umbrales estilo CRAG.

**Fase 2 — juez de suficiencia**, SOLO si la fase 1 no alcanza. Caveat del propio paper: la
suficiencia NO detecta el contexto enganoso, y abstenerse por insuficiencia a secas bota
respuestas correctas (35-62% aciertan igual).

**Fase 3 — garantia conformal**, alpha=0.1 con dev=114 (n=102 requerido). Para alpha=0.05,
usar el set de 339.

---

## 10. Lo que NO se pudo verificar

- Tabla exacta de AUROC del paper de Nature de entropia semantica (de pago; solo el blog de
  los autores).
- AUROC primario del score de reranker como senal de abstencion: **no se hallo fuente
  primaria**, solo blogs.
- Precision de un autorater de suficiencia con modelo abierto 7-30B: no existe numero
  publicado.
- Soporte de español de HHEM-2.3 comercial: afirmacion del proveedor, sin verificar.
- Claims de "reduce alucinaciones" de Guardrails AI: blog, sin respaldo cuantitativo.
- NeMo self-check-facts y Azure groundedness: sin numero de precision en su propia doc.
- El artefacto "el vecino casi-duplicado vuelve trivial la remocion": inferido de por que los
  4 papers evitan la remocion, no nombrado literalmente en ninguno.
- Papers con ID arXiv 26xx: leidos en HTML, son recientes y de menor recorrido que el resto.

## Fuentes primarias leidas

Stanford/JELS: https://dho.stanford.edu/wp-content/uploads/Legal_RAG_Hallucinations.pdf ·
Sufficient Context: https://arxiv.org/pdf/2411.06037 ·
CRAG: https://arxiv.org/html/2401.15884v3 ·
Semantic Uncertainty: https://arxiv.org/html/2302.09664 ·
Can LLMs Express Their Uncertainty: https://arxiv.org/html/2306.13063 ·
Just Ask for Calibration: https://arxiv.org/html/2305.14975 ·
Conformal Language Modeling: https://arxiv.org/html/2306.10193 ·
Conformal Factuality: https://arxiv.org/html/2402.10978v1 ·
Gentle Intro to Conformal: https://arxiv.org/html/2107.07511v6 ·
UAEval4RAG: https://arxiv.org/html/2412.12300 ·
RGB: https://arxiv.org/pdf/2309.01431 ·
CRUMQs: https://arxiv.org/html/2510.11956 ·
GRAB-RAG (contexto enganoso): https://arxiv.org/html/2608.22228 ·
SQuAD2.0: https://arxiv.org/pdf/1806.03822 ·
Selective QA: https://ar5iv.labs.arxiv.org/html/2006.09462 ·
LegalBench-RAG: https://arxiv.org/abs/2408.10343 ·
CLERC: https://arxiv.org/abs/2406.17186 ·
HHEM: https://huggingface.co/vectara/hallucination_evaluation_model
