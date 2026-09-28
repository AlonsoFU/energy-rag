# 01 · Arquitectura: de la pregunta a la respuesta

Punto de entrada: `scripts/preguntar.py`. Lógica: `src/pipelines/retrieve.py` (búsqueda) y
`src/pipelines/generate.py` (redacción). Configuración: `src/core/config.py` (los defaults SON la
configuración adoptada) + `.env`.

## Flujo

![Pipeline de Energy-RAG](pipeline.svg)

El mismo flujo con los tiempos medidos, etapa por etapa:

```
Pregunta
  │
  ▼
BÚSQUEDA (SimpleRetriever.retrieve)                              21.7 s en total
  ├─ BM25 sobre Postgres (palabras exactas)                        0.00 s
  ├─ Vector: Qwen3-Embedding 4B vía Ollama (CPU), pgvector        0.16 s
  │          columna embedding_4b_1024 (prefijo MRL de 1024)
  └─ Alias coloquial→legal + glosario (definiciones inyectadas)
  │
  ▼
Fusión RRF → pool de 50 candidatos
  │  (excluye artículos derogados, fantasmas y duplicados)
  ▼
Reranker BGE-reranker-v2-m3: ordena 30 → deja 10               21.5 s CPU / 2.9 s GPU
  │
  ├── --buscar ──► muestra los 10 artículos con su texto          13 s por consulta
  │
  └── con respuesta
        ▼
      Redacción: qwen3:30b-a3b (Ollama, local), temperatura 0, 1 muestra
        ▼
      Verificador de citas (modo quote-only)
        · cada cita debe ser un fragmento TEXTUAL del artículo citado (substring exacto)
        · máximo 2 citas
        · reatribución: si la frase está en un único artículo, se cita ese
        · si ninguna cita calza → prosa con el aviso «SIN CITA VERIFICADA»
        ▼
      Pantalla: los 10 artículos arriba + resumen abajo «verifíquelo»    ~79 s
```

## Configuración adoptada (defaults de `config.py`)
| parámetro | valor | por qué / medición |
|---|---|---|
| `embed_4b_dense`, `embed_4b_dim` | True, 1024 | Qwen3-Embedding 4B, mejor que 0.6B; MRL 1024 indexable con HNSW |
| `embed_4b_num_ctx` | 4096 | el embedder cargaba 9.8 GB de RAM con 32768; vectores idénticos (coseno 1.000000) |
| `alias_union`, `glossary_inject`, `glossary_lookup` | True | puente coloquial→legal; `glossary_inject` fue el mayor salto de búsqueda (+16) |
| `retrieval_pool_depth` / `top_rerank_override` | 50 / 30 | pool que ve el reranker |
| `use_bge_reranker` | True | BGE-v2-m3; en CPU por defecto (ver abajo) |
| `filtrar_derogados`, `filtrar_duplicados`, `filtrar_fuera_dominio` | True | no servir ley muerta ni copias |
| `answer_quote_only`, `answer_quote_max` | True, 2 | la respuesta son citas textuales verificadas |
| `answer_quote_reatribuir` | True | exp #77/#83 |
| `answer_prosa_marcar` | True | aviso «SIN CITA VERIFICADA» (exp #78/#83) |
| `selfcons_temperature`, `self_consistency_n` | 0.0, 1 | reproducible y 1 llamada (exp #79, #86) |
| `ollama_num_ctx` | 32768 | NO bajar: con razonamiento la salida llegó a ~17k tokens; cortar trunca en silencio |

## El reranker y la GPU
- En **CPU** por defecto (`src/components/reranker.py`, `BGE_DEVICE`). En GPU fp32 ordena **igual**
  (194/194) y es 7× más rápido, pero **desplaza al LLM** de respuestas: 49/49 → 43/49 capas en GPU
  (el LLM a ctx 32768 ocupa 22 de 24.5 GB). fp16 no lo arregla y además cambia 73/194 órdenes.
- `preguntar.py --buscar` sí usa GPU (no carga LLM de respuestas) si hay ≥ 4 GB de VRAM libre.

## Trampa de configuración
`config.py` trae `llm_default = "claude-sonnet-4-6"` (API pagada) y `.env` tiene una
`ANTHROPIC_API_KEY`. Lo que manda hoy es `.env`: `LLM_DEFAULT=ollama/qwen3:30b-a3b`. Si `.env`
falta, el sistema caería a la API pagada. Para ordenar el repo: dejar el default local en código.

## Componentes y archivos
| pieza | archivo |
|---|---|
| CLI de consulta | `scripts/preguntar.py` |
| búsqueda | `src/pipelines/retrieve.py` (`SimpleRetriever`, `_embed_4b_query`, `_vector_4b_search`) |
| alias coloquiales | `src/pipelines/alias_map.py` |
| reranker | `src/components/reranker.py` (`BGEReranker`) |
| redacción + verificador | `src/pipelines/generate.py` (quote-only, `_self_consistency`, aviso) |
| extracción de citas | `src/pipelines/grounding.py` (`extract_citations`) |
| acceso a la base | `src/components/vectorstore.py` (`PostgresStore`), `src/storage/connection.py` |
| LLM | `src/components/llm.py` (litellm → Ollama; timeout 300 s por intento) |
| bitácora de preguntas reales | `src/core/bitacora.py` (tabla `consultas_log`, 33 filas) |
