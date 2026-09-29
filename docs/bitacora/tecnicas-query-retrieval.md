# Registro de técnicas de query/retrieval — probadas y disponibles

> Referencia viva de qué técnicas de reformulación/razonamiento de query se probaron en Energy-RAG,
> su resultado y su estado en el código. Acompaña `architecture-status.md` §8.

## Sustento anti-alucinación (vale para TODAS las de abajo)
La reformulación (HyDE, Query2Doc, etc.) genera texto que se usa **solo para RETRIEVAL** (calcular el
vector de búsqueda); ese texto **se descarta** y **nunca se cita**. La respuesta se genera desde los
**artículos reales recuperados** y el **verificador de grounding** exige que toda cita exista en el
corpus. ⇒ La reformulación **no puede producir una cita falsa**; su único riesgo es **retrieval drift**
(traer el artículo equivocado), que se mide con cita_ok/recall, no con grounding.

## Tabla de técnicas
| # | Técnica | Idea | Estado en el sistema | Resultado medido |
|---|---|---|---|---|
| 1 | **HyDE** | Inventa una respuesta legal hipotética y embebe eso | Flag `hyde_in_simple`, default **OFF** | +1 marginal en coloquial; overfit en dev (held-out lo reveló) |
| 2 | **Query2Doc** | Como HyDE pero CONCATENA con la query original (aditivo) | No implementado | — (candidato seguro) |
| 3 | **Step-Back** | Abstrae a la pregunta general/principio | **Activo** en `ComplexRetriever` (rama complejo) | empató (+1) en coloquial |
| 4 | **Multi-Query / RAG-Fusion** | N variantes + fusión RRF | **Activo** en `ComplexRetriever` | empató (+1) |
| 5 | **RePhraseQuery** | Reescribe coloquial → consulta limpia | No implementado | — |
| 6 | **Intent + Entity extraction** | Infiere el concepto/organismo legal y da términos formales | Probado retrieval-only (`exp_intent_extraction.py`), NO adoptado | marginal/wash: coloquial +1 (8→9/11), dev **−1** (drift: LLM extrae términos alucinados, ej. "NCh 1082"); el SEC duro afloró a rank 18, no top-10 |
| 7 | **Decomposition / Sub-question** | Parte en sub-preguntas | **Descartada** (no está en el pipeline) | negativo: rompió ext_hundida (6→4) |
| 8 | **CoT query** | Razona en voz alta y luego emite la consulta | No implementado | — (variante de #6) |
| 9 | **Self-Query (filtros)** | Extrae filtros de metadata (norma/año) | Parcial: visto en `exp_authority` (detección de norma) | el boost por norma no discriminó (pool ya 60% de la norma) |
| 10 | **Query Expansion (sinónimos)** | Agrega sinónimos al lado léxico | Diccionario curado: **descartado** | contraproducente (rompió rechazo off-topic) |
| 11 | **Routing por intención** | Enruta a léxico/vector/grafo según intención | Parcial: router simple↔complejo (`AdaptiveRouter`) | en uso |
| 12 | **Adaptive (CRAG/Self-RAG)** | Busca → evalúa relevancia → reescribe/reintenta | Parcial: **gate semántico** (rechaza si bge_max<τ) | adoptado (flag OFF): +2 coloquial, 0 regresión |

## Otras palancas probadas (no de query)
- **BGE cross-encoder reranker**: ADOPTADO (default ON). +cita_ok dev/holdout, grounding intacto.
- **Term-prefix de glosario** (contextual determinista): DESCARTADO (net 0, regresión por competencia).
- **Contextual Retrieval (Anthropic, contexto LLM por chunk)**: scoped, NO rescató los duros. Revertido.
- **Embedder swap bge-m3** (mismo tamaño que Qwen3-0.6B): NO ayudó coloquial (5/11=igual), −2 neto. Revertido.
- **Gate off-topic semántico** (bge_max<τ): ADOPTADO (flag OFF). Reemplaza el guard léxico que rechazaba coloquiales.

## Frentes futuros (documentados, no hechos)
- **Embedder genuinamente más grande** (Qwen3-Embedding-4B/8B): sin probar; 8B no entra en GTX 1080.
- **Intent/Entity extraction (#6)**: el próximo lever de query recomendado (genérico, seguro).
- **Fine-tune Tulio/Patana → embedder chileno**: solución específica, alto esfuerzo, congelada.

## Prompts de referencia (los 2 sin probar más prometedores)
**#6 — Intent/Entity extraction:**
```
Eres experto en normativa eléctrica chilena. Dada la pregunta de un usuario,
identifica el concepto, organismo o institución legal que la responde.
Devuelve SOLO los términos legales formales, sin explicar.
Pregunta: {query}
Términos legales:
```
**#2 — Query2Doc (aditivo):**
```
Escribe 1-2 frases en lenguaje legal formal que respondan esta pregunta.
Pregunta: {query}
Respuesta formal:
```
→ `texto_de_búsqueda = query + " " + respuesta_formal` (conserva la query original).
