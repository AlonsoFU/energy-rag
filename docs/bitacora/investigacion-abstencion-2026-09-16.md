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

Ver `docs/bitacora/plan-operacion.md`, seccion DIAGNOSTICO 2026-09-16. Resumen: `n_cits` y `n_uniq`
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

---

# SEGUNDA RONDA (8 agentes) — el plan de la seccion 9 queda SUPERADO

## 11. El plan estaba mal priorizado (agente adversario, evidencia primaria)

**11.1 Limpiar datos rinde mas que agregar maquinaria.** OHR-Bench (2412.02592) mide exactamente
nuestra falla: contaminacion de parseo propagandose por el pipeline. Con el MEJOR extractor
(Qwen2.5-VL-72B) la caida end-to-end sigue siendo **14% relativo (5 puntos F1)**; con ruido
SEMANTICO severo (tokens equivocados, no formato) la caida llega a **~50%**; un parser medio
(MinerU 30.0 F1) pierde ~17% relativo contra texto limpio (36.1 F1).
Nuestros **598 articulos con notas BCN incrustadas son el mismo defecto**: metadato del editor
contaminando la unidad de cita.
Complemento (2603.24580): subir metricas de retrieval **no garantiza** mejores respuestas cuando
el retrieval ya es decente.

**11.2 Nuestros evals sinteticos inflan los resultados. Medido.**
- Consultas generadas por LLM **sobreestiman Recall@10 entre 9% y 20.7%** frente a consultas
  reales de produccion (Chroma, Generative Benchmarking).
- **11.91% de las consultas generadas son casi-duplicados** (coseno >=0.9) del documento fuente
  -> filtracion que hace parecer facil la busqueda.
- Rahmani et al. (2506.10301) confirma por separado: las colecciones sinteticas son
  "consistently easier" y sobreestiman en todos los tipos de sistema.
- **Consecuencia directa:** las fases 0b/0c/1 que yo propuse construyen MAS negativos sinteticos
  y ajustan un umbral sobre ellos. Es invertir justo donde el sesgo medido es mayor, con CERO
  consultas reales para corregirlo.

**11.3 La abstencion cuesta caro.** Kamath et al. (2006.09462): el metodo selectivo CALIBRADO
responde solo el **56%** de las preguntas para sostener 80% de exactitud; el umbral ingenuo
(MaxProb, el analogo de "senales gratis") solo **48%**. O sea: una version bien hecha de lo que
propuse **rechaza >40%** de las consultas. Es decision de producto, no mejora gratis. Ademas los
modelos son sobreconfiados FUERA de dominio -> un umbral ajustado en sintetico nace descalibrado.

**11.4 Lo mas efectivo ya esta construido.** Dahl et al. (2401.01301): GPT-4 sin restriccion
alucina citas legales **58%** de las veces; la solucion en la que converge el area es forzar
verificacion contra la fuente = nuestro modo quote-only.

## 12. Nuestro eval es MAS ESTRICTO que la literatura de atribucion

- **ALCE (2305.14627)** define citation recall/precision **por implicacion (NLI)**, nunca contra
  el ID del documento gold. Si citamos el articulo B y B contiene texto parecido, ALCE lo puntua
  **correcto**. AIS (2112.12870) y AutoAIS (2212.08037) comparten el mismo punto ciego.
- **Por eso #77 dio cero:** cuando dos normas tienen redaccion paralela, ni el mecanismo ni las
  metricas del area distinguen "texto duplicado, cualquiera sirve" de "documento equivocado".
- **Ninguna taxonomia tiene la categoria** (ALCE, RAGTruth 4 clases, taxonomia de 16 tipos). La
  unica etiqueta parecida es "misgrounded" de Stanford/JELS, y es **anotacion manual**.
- AutoAIS correlaciona r=0.96 con humanos **a nivel de sistema**; el propio paper advierte que a
  nivel de instancia es "much lower and more variable".
- Dato lateral (2412.18004): hasta **57% de las citas que SI implican la afirmacion** no fueron
  causalmente usadas para generarla (racionalizacion posterior).
- **Veredicto: no existe metodo medido y reproducible para nuestro bug exacto.**

## 13. Recuperacion a nivel de articulo

- Nuestro bug tiene nombre: **Document-Level Retrieval Mismatch (DRM)** — el retriever trae el
  tipo de texto correcto desde el documento equivocado (2510.06999). Arreglo propuesto:
  **Summary-Augmented Chunking** (anteponer a cada chunk un resumen del documento).
  **Numeros NO verificados** (el PDF no parseo; solo el abstract).
- **Lo mejor documentado es afinar el retriever denso.** CLERC (2406.17186): ft-LegalBERT-DPR
  nDCG@10 **14.67** vs BM25 zero-shot **5.40**; recall@1K 68.5% vs 48.3%. El dominio pesa mas que
  la arquitectura.
- Chunking que respeta limites estructurales (LegalBench-RAG, 2408.10343): **P@1 6.4% vs 2.4%**
  (~2.7x) pero **R@64 62.2% vs 76.4%** (peor recall). Es sobre contratos, no leyes.
- Lo que gana benchmarks de statutes (COLIEE Task 3) es BM25 + reranker neuronal en dos etapas =
  lo que ya corremos (CAPTAIN F2~0.764, JNLP~0.753).
- **Huecos reales:** nadie aislo "chunking estructural" como variable controlada sobre texto de
  ley; y **las notas de enmienda incrustadas no tienen respuesta en la literatura**. Los 598
  articulos los resolvemos solos y lo medimos contra nuestro propio eval.

## 14. Senales: el score del reranker NO alcanza solo

- **No existe paper primario** que mida calibracion (ECE/Brier) ni AUROC de scores de
  cross-encoder (BGE/monoT5/MiniLM/ColBERT) para abstencion. Buscado a proposito en cs.IR,
  SIGIR, ECIR, TOIS. Solo blogs. **Hueco confirmado.**
- Lo mas cercano medido (2606.29959): margen top1-top2 **en logits del LLM**, AUROC **0.719**
  (TriviaQA) / 0.657 (NQ) / 0.583 (MS MARCO) — por DEBAJO de entropia (0.694-0.810).
- **Calibrar bajo el ECE de 0.185 a 0.039 pero NO cambio el AUROC.** Calibrar reordena
  probabilidades, no mejora la separacion. Calibrar no salva una senal debil.
- **Ningun sistema del SOTA usa umbral crudo sobre score del buscador**: CRAG entrena T5-large
  (84.3%), Self-RAG entrena token ISREL, FLARE usa prob de generacion, Adaptive Retrieval usa
  popularidad de entidad.
- QPP (el campo clasico de IR para "saldra bien esta query"): Kendall tau **0.05-0.35**, debil,
  y nadie la uso para abstencion en RAG.

## 15. Entropia semantica: numeros primarios (Nature SI, CC-BY)

- Modelo de clustering: **DeBERTa-large NLI**. GPT-3.5 como alternativa barata; GPT-4 solo para
  calificar exactitud.
- **M=10 en los resultados principales**; texto explicito: "after roughly M=5 there are
  diminishing returns, although going up to M=10 can still help". **No hay minimo duro.**
  Nuestro n=3 sigue por debajo de lo probado.
- AUROC promedio sobre 60 combinaciones modelo x dataset (respuesta corta): **SE 0.792**,
  SE discreta 0.790, entropia naive 0.760, **p(True) 0.683**, regresion sobre embeddings 0.708.
- Ablacion del modelo de implicacion (LLaMA-2-70B, 8 generaciones): DeBERTa prom **0.78**
  (TriviaQA 0.83), GPT-3.5 0.83, GPT-4 0.80, LLaMA-2-70B como juez 0.71.
- Acuerdo humano: implicacion Humano-Humano 87%, Humano-GPT-4 87%.

## 16. Jueces chicos y abiertos (dato que faltaba para decidir la fase 2)

LLM-AggreFact (balanced accuracy): **Bespoke-MiniCheck-7B 77.4** > Claude-3.5-Sonnet 77.2 >
gpt-4o 75.9 > Qwen2.5-72B 75.6 > **MiniCheck-FT5 (0.8B) 75.0** > Llama-3.3-70B 74.5.
- **Un verificador AFINADO de 0.8B empata con GPT-4o.** Pero ningun modelo chat generico de
  7B-32B aparece en estos leaderboards como juez: los unicos chicos que llegan son fine-tunes
  especializados. **Un Qwen local sin afinar no tiene numero publicado.**
- **FaithBench (NAACL 2025), casos adversariales:** TODO se cae a cerca del azar. Mejor sistema
  62.31% BA; GPT-4o 56.18%; MiniCheck-DeBERTa 55.21%; **HHEM-2.1-Open 51.98%**.
- Sesgos de juez (secundario, no verificado a fondo): auto-preferencia ~10-25 pts, verbosidad
  ~15-30 pts, posicion ~10-15 pts.

## 17. Español es MAS DIFICIL. Evidencia directa

**Mu-SHROOM (SemEval-2025 Task 3)**, deteccion de spans alucinados en 14 idiomas:
**español quedo ULTIMO, 14/14, IoU medio 0.31** (italiano 1ro con 0.51). Mejor sistema en español
IoU 0.53. El acuerdo entre anotadores en español tambien fue de los mas bajos (0.45 val /
0.51 test).
-> Cualquier numero de deteccion de alucinaciones sacado de papers en ingles **no se transfiere**.
- **HHEM-2.1-Open es solo ingles** (el español esta solo en la version comercial 2.3).
- **Azure groundedness: solo ingles, sin ninguna cifra publicada.**
- NeMo self-check-facts: **80%** (2310.10501, autoria del propio proveedor) — unico numero que
  existe.
- **Sin evidencia** sobre si la abstencion transfiere entre idiomas. Hueco abierto.

## 18. NLI en español, offline

| modelo | params | XNLI es | licencia | verificado |
|---|---|---|---|---|
| **mDeBERTa-v3-base-xnli-multilingual-nli-2mil7** | 279M | **83.2%** | MIT | model card del autor |
| XLM-RoBERTa-large-XNLI | 560M | arquitectura base 85.1% es | MIT | inferido, la card no da tabla |
| Recognai/bert-base-spanish-wwm-cased-xnli (BETO) | 110M | 79.9% | MIT | model card |
| PlanTL-GOB-ES | — | **no existe checkpoint NLI** | — | buscado en su org HF |

- **No existe dataset ni modelo NLI legal en español.** Usar mDeBERTa sobre normativa chilena es
  transferencia de dominio **no probada**; hay que etiquetar 30-50 pares a mano antes de confiar.
- Costo estimado (no medido): n=5 -> 20 pases por query -> ~2280 pases para dev = 1-4 min.

## 19. Deteccion del lado de la consulta + evidencia con usuarios

- **Mahalanobis** sobre embeddings gana en falsos aceptados: **FPR95 6.8 vs 11.6** (CLINC150),
  y 0.5 vs 2.2 en ROSTD (4x). Tenemos 2960 articulos para ajustar centroides/covarianza.
- **No hay ganador universal** (2109.06827): en desplazamiento SEMANTICO (nuestro caso: mismo
  dominio, norma equivocada) ganan los metodos tipo calibracion; en desplazamiento de fondo gana
  densidad/perplejidad.
- **Hueco real:** nadie aplico deteccion OOD a consultas contra un corpus fijo de recuperacion.
- **Baño de humildad (SQuAD 2.0):** mejor modelo 66.3 F1, humano 89.5, y **abstenerse SIEMPRE da
  48.9 F1**. Los clasificadores de "no tiene respuesta" son debiles incluso con el contexto.
- **Contrapeso (Adaptive-RAG 2403.14403):** su clasificador acierta solo **54.52%** y aun asi el
  sistema mejora y baja ~55% la latencia. Una compuerta mediocre puede rendir.
- **HCI, n=184 (2402.07632):** confianza **bien calibrada +20%** de exactitud (IC95 0.18-0.23);
  **mal calibrada +2%** (IC95 -0.00-0.04) **y AUMENTA el sesgo de automatizacion**.
  -> Mostrar un nivel de confianza sin calibrar **es daniño**, no neutro. No mostrar nada hasta
  tener la curva riesgo-cobertura medida.

## 20. Obligaciones legales: NINGUNA vinculante aplica

- **AI Act (UE 2024/1689)**: Anexo III(8)(a) cubre sistemas usados **por o para autoridades
  judiciales**, no herramientas de investigacion legal. Art. 6(3) exime ademas tareas
  procedimentales estrechas (recuperacion/clasificacion de documentos es el ejemplo de los
  considerandos). Art. 50 (transparencia) aplicaria solo si fuera producto publico. Aplicacion
  general 2 ago 2026. Y es jurisdiccion UE: proyecto chileno queda fuera igual.
- **Chile**: no hay ley vigente. Proyecto (boletines 15.869-19 + 16.821-19 refundidos) aprobado
  en primer tramite en la Camara el 13 oct 2025, ahora en el Senado. **Circular N°711 (2024)**
  del Ministerio de Ciencia rige solo para organismos del Estado.
- **ABA Formal Opinion 512 (29 jul 2024)**: obliga al **humano** a verificar. No puede imponerle
  nada al sistema.
- **NIST AI 600-1 (jul 2024)**: voluntario y de PROCESO. Define "confabulation" incluyendo
  "confabulated logic or citations". Acciones concretas: **MS-2.5-003** (verificar fuentes y
  citas antes de desplegar y en monitoreo continuo), MG-4.1-002 (monitoreo post-despliegue),
  MG-4.1-004, MG-4.3-002 (registrar errores y cuasi-fallas), MG-3.2-009.
- **Dato empirico que si justifica todo esto:** el registro publico de casos judiciales con
  alucinaciones va en **2.041 casos** (datos al 14 sep 2026), **1.690 de ellos citas
  fabricadas**; EEUU 1.395, Canada 217, Australia 111. Crece ~1 caso por dia.
- **Veredicto:** quote-only, tope 2 y rechazo cuando no encuentra es **criterio de ingenieria
  informado**, respaldado por evidencia empirica, no exigido por ninguna norma.

---

# PLAN FINAL (reemplaza la seccion 9)

Orden por rendimiento medido esperado, no por elegancia:

**A. Limpiar los 598 articulos con notas BCN.** Es la palanca con mayor respaldo (OHR-Bench:
10-50%). Ataca a la vez el 17% en prosa (causa raiz ya diagnosticada) y probablemente parte de
las 29/103. Criterio fijado antes: cita_ok y cita_limpia en dev y held-out, mas recuento de
articulos con etiqueta contaminada. Sin regex como mecanismo principal (regla del proyecto).

**B. Conseguir 50-100 consultas reales ANTES de ajustar cualquier umbral.** Todo lo aguas abajo
es invalido sin esto: sobreestimacion medida de 9-20.7%, 11.91% de casi-duplicados, y
sobreconfianza fuera de dominio.

**C. Diagnosticar la raiz de las 29/103** (misgrounded). Hipotesis a separar: contaminacion de
etiqueta (A lo arregla), redaccion paralela entre normas (entonces el gold es discutible y el
eval esta mal), o mezcla de rankings. **Ninguna herramienta del area detecta esto**; es
diagnostico propio.

**D. Instrumentar senales** (`_bge_max`, margen, acuerdo entre muestras, n citas verificadas).
Barato, no cambia respuestas. Pero **no confiar en umbral crudo**: sin evidencia primaria, y el
analogo medido da AUROC 0.58-0.72.

**E. Abstencion**, recien despues de A-D, sabiendo el precio: **>40% de rechazo** para sostener
80% de exactitud. Es decision de producto y hay que preguntarla, no asumirla.

**F. Mostrar confianza al usuario: NO, hasta tener la curva medida.** Mal calibrada da +2% y
aumenta el sesgo de automatizacion.

**G. Conformal: aplazado.** Sin consultas reales no hay distribucion de calibracion valida.

**Descartado por evidencia:** juez de suficiencia como primer paso (ningun modelo chat generico
chico tiene numero publicado como juez; en casos adversariales todos caen cerca del azar);
negativos sinteticos como base de calibracion (sesgo medido); metricas de atribucion estandar
(ALCE/AIS/AutoAIS son ciegas al ID del documento, mas laxas que nuestro eval actual).

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

## Fuentes primarias leidas — SEGUNDA RONDA

Nature semantic entropy (SI, CC-BY):
https://ora.ox.ac.uk/objects/uuid:0653d09e-9368-4eb1-98bb-50d9dda7d3e5/files/r0g354g31t ·
Mu-SHROOM SemEval-2025 (español ultimo de 14): https://aclanthology.org/2025.semeval-1.322.pdf ·
FaithBench NAACL 2025: https://aclanthology.org/2025.naacl-short.38.pdf ·
LLM-AggreFact leaderboard: https://llm-aggrefact.github.io/ ·
MiniCheck: https://arxiv.org/html/2404.10774v2 ·
ALCE: https://arxiv.org/html/2305.14627 · AIS: https://arxiv.org/abs/2112.12870 ·
AutoAIS / Attributed QA: https://ar5iv.labs.arxiv.org/html/2212.08037 ·
RARR: https://ar5iv.labs.arxiv.org/html/2210.08726 ·
Attribute-First-Then-Generate: https://ar5iv.labs.arxiv.org/html/2403.17104 ·
Correctness is not Faithfulness: https://arxiv.org/abs/2412.18004 ·
RAGTruth: https://ar5iv.labs.arxiv.org/html/2401.00396 ·
OHR-Bench (calidad de parseo): https://arxiv.org/html/2412.02592v4 ·
Synthetic vs real queries: https://www.trychroma.com/research/generative-benchmarking ·
Rahmani et al. (colecciones sinteticas): https://arxiv.org/pdf/2506.10301 ·
Retrieval gains != answer gains: https://arxiv.org/pdf/2603.24580 ·
Seven Failure Points: https://arxiv.org/abs/2401.05856 ·
Kamath selective QA: https://arxiv.org/abs/2006.09462 ·
Dahl et al. alucinacion legal: https://arxiv.org/abs/2401.01301 ·
DRM / Summary-Augmented Chunking: https://arxiv.org/abs/2510.06999 ·
LeSICiN: https://ar5iv.labs.arxiv.org/html/2112.14731 ·
COLIEE 2023 overview: https://pmc.ncbi.nlm.nih.gov/articles/PMC11026282/ ·
Margen de logits / Know Before You Fetch: https://arxiv.org/html/2606.29959 ·
TARG: https://arxiv.org/abs/2511.09803 ·
Shallow Cross-Encoders: https://arxiv.org/abs/2403.20222 ·
Mahalanobis OOD: https://arxiv.org/pdf/2101.03778 ·
Tipos de OOD: https://arxiv.org/html/2109.06827 ·
CLINC150: https://arxiv.org/pdf/1909.02027 ·
When Not to Trust LMs: https://arxiv.org/html/2212.10511 ·
FLARE: https://arxiv.org/html/2305.06983 ·
Adaptive-RAG: https://arxiv.org/html/2403.14403 ·
HCI confianza calibrada (n=184): https://arxiv.org/abs/2402.07632 ·
mDeBERTa-xnli: https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7 ·
XNLI: https://arxiv.org/abs/1809.05053 · XLM-R: https://ar5iv.labs.arxiv.org/html/1911.02116 ·
NIST AI 600-1: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf ·
AI Act Anexo III: https://artificialintelligenceact.eu/annex/3/ ·
AI Act art. 50: https://artificialintelligenceact.eu/article/50/ ·
Registro de casos con alucinaciones: https://www.damiencharlotin.com/hallucinations/ ·
NeMo Guardrails: https://arxiv.org/abs/2310.10501

## Advertencias sobre la segunda ronda

- Varios PDF no parsearon (Stanford por un agente, DRM 2510.06999, QPP de Ferro). Lo marcado
  como no verificado esta indicado en cada seccion.
- Los numeros de sesgo de juez (auto-preferencia, verbosidad, posicion) vienen de resumenes de
  busqueda, no de tabla leida.
- Papers con ID arXiv 25xx/26xx: recientes, menos recorrido que el resto.
- HHEM: las cifras altas son del propio proveedor; en FaithBench (academico, adversarial) cae a
  51.98%.
