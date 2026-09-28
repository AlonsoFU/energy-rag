# Energy-RAG — documentación del sistema (vigente al 2026-09-21)

Sistema de consulta sobre normativa eléctrica chilena: busca los artículos que responden una
pregunta y, si se pide, redacta un resumen con citas textuales verificadas. Todo corre en local
(Postgres + pgvector, Ollama, GPU RTX 3090); no usa APIs pagadas.

Esta carpeta es **la verdad vigente, dividida por tema**. Los `docs/handoff-*.md` y
`docs/plan-operacion.md` son la bitácora histórica (qué se probó, cuándo y por qué); no hace
falta leerlos para entender el sistema.

| tema | archivo | responde a |
|---|---|---|
| Arquitectura | [01-arquitectura.md](01-arquitectura.md) | ¿qué pasa desde que llega una pregunta hasta que sale la respuesta? |
| Corpus y datos | [02-corpus-y-datos.md](02-corpus-y-datos.md) | ¿qué hay en la base, qué defectos tuvo, cómo se reparó y cómo se revierte? |
| Actualización desde BCN | [03-actualizacion-bcn.md](03-actualizacion-bcn.md) | ¿cómo se entera el sistema de que una ley cambió? |
| Evaluación | [04-evaluacion.md](04-evaluacion.md) | ¿cómo se mide, con qué preguntas, y qué trampas tiene medir? |
| Operación | [05-operacion.md](05-operacion.md) | ¿cómo se usa, cómo se corren experimentos largos, cómo se cuida la GPU? |
| Resultados y límites | [06-resultados-y-limites.md](06-resultados-y-limites.md) | ¿qué tan bien funciona, qué se probó y falló, qué falta? |

Diagrama de bloques: artefacto "Energy-RAG por dentro" (claude.ai/code/artifacts).

## En 6 líneas
1. **Uso correcto hoy: buscador interno con una persona que lee la fuente.** No responde solo a terceros.
2. Artículo correcto: dev **83/114**, held-out **62/64**, preguntas reales de terceros **10/16**.
3. Cuando se equivoca casi nunca avisa (reales: 5 de 6 errores sin advertencia): copia textual un artículo real que no es el que responde.
4. `preguntar.py --buscar` tarda **13 s**; con respuesta **~79 s** (21.5 s son el reranker en CPU).
5. El cuello de precisión es la **búsqueda de preguntas coloquiales** (18 de 31 fallas de dev: el artículo correcto nunca llega).
6. Siguiente paso de precisión (trabajo futuro): afinar el buscador denso con pares pregunta coloquial → artículo.
