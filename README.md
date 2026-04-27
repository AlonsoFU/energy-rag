## v1: Postgres + LLM (April 2026)

The system has been rewritten on top of PostgreSQL + pgvector + Claude API.
See `docs/superpowers/specs/2026-04-26-rag-normativa-electrica-design.md`
for the design and `docs/superpowers/plans/2026-04-26-rag-normativa-electrica.md`
for the implementation plan.

### Quick start

```bash
sudo apt install postgresql-16 postgresql-16-pgvector
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # edit with ANTHROPIC_API_KEY and DB credentials
alembic upgrade head
python scripts/migrate_to_postgres.py            # one-shot migration of JSON normas
python scripts/embed_all.py --skip-contextual --mock --limit 200  # quick test
python -m src ask "¿qué es COMA?" --mock
```

The legacy code under `src/search/` is deprecated; new code lives in
`src/components/`, `src/pipelines/`, `src/extraction/`, `src/routing/`,
`src/eval/`, and `src/cli.py`.

---

# Buscador de Normas Eléctricas Chile (BCN)

Sistema de búsqueda semántica + grafo de conocimiento (GraphRAG) sobre normas legales del sector eléctrico chileno, extraídas desde la Biblioteca del Congreso Nacional (BCN).

## Qué hace

Dado un concepto técnico del sector eléctrico (ej: "COMA", "potencia firme", "transferencias de potencia"), el sistema:

1. **Encuentra** los artículos más relevantes entre 2,147 artículos de 103 normas
2. **Sabe** qué norma *define* el concepto vs cuál solo lo *aplica* o *menciona* (grafo de conocimiento)
3. **Prioriza** los reglamentos base que contienen la definición original

### Ejemplo

```
Query: "COMA"

Resultado:
  1. D.S. N°10 (2019) [Reglamento base] ★ define concepto
     Art. 2° - "COMA: Costo de Operación, Mantenimiento y Administración..."

  2. D.S. N°37 (2019) [Reglamento base] ★ define concepto
     Art. 3° - "COMA: Se entenderá por..."

  3. D.S. N°61 (2011) [Fija valores] ★ aplica concepto
     Art. 1° - "Fíjase el valor de COMA en..."
```

Sin el grafo, el sistema devolvería cualquier artículo que mencione "COMA" sin distinguir cuál es la fuente autoritativa.

## Estado actual

### Lo que funciona bien

- **Búsqueda híbrida**: BM25 (léxica) + embeddings semánticos + RRF fusion + cross-encoder reranking. Encuentra artículos relevantes con buena precisión.
- **Grafo de conocimiento**: 131 nodos (102 normas + 29 conceptos), 238 aristas. Construido sin LLM, usando regex sobre secciones de glosario + referencias cruzadas. Distingue correctamente norma base vs derivada.
- **Clasificación de normas**: Detecta automáticamente si un decreto es `reglamento_base`, `fija_valores`, `modifica` o `deroga`.
- **Graph boost**: Prioriza resultados según la relación norma-concepto (define > aplica > menciona > referencia).
- **Filtro de ruido**: Cuando el grafo tiene contexto, solo muestra normas relevantes.

### Lo que falta

- **Generación de respuestas**: El sistema devuelve artículos, no respuestas en lenguaje natural. Falta conectar un LLM (Claude, Llama) para que sintetice la información.
- **Cobertura**: Solo 103 de 2,031 normas tienen texto completo descargado. El resto tiene solo metadatos.
- **Conceptos**: Solo 29 conceptos de ~8 normas con glosario explícito. Muchas normas definen términos fuera de secciones de glosario.
- **Temporalidad**: El grafo no distingue versiones vigentes vs derogadas de una misma norma.
- **Evaluación**: No hay métricas formales de calidad (precision, recall). La validación ha sido manual.

## Arquitectura

```
                 RETRIEVAL (funciona)              GENERATION (pendiente)
              ┌───────────────────────┐          ┌──────────────────┐
              │                       │          │                  │
Query ──┬────►│  BM25 (léxica)  ──┐  │          │                  │
        │     │                    ├──┼── RRF ──►│  LLM (Claude)   │──► Respuesta
        └────►│  FAISS (semántica)─┘  │  fusion  │  (por agregar)  │    en lenguaje
              │                       │    +     │                  │    natural
              │  ┌──────────────┐     │ reranker └──────────────────┘
              │  │ GRAFO        │     │    +
              │  │ 102 normas   │     │  graph
              │  │ 29 conceptos │     │  boost
              │  └──────────────┘     │
              └───────────────────────┘
```

### Pipeline de búsqueda (por query)

1. **BM25** - Ranking léxico sobre 2,147 artículos tokenizados
2. **Embeddings** - Similitud coseno con `multilingual-e5-base` (768-dim) vía FAISS
3. **RRF** (Reciprocal Rank Fusion) - Combina ambos rankings en uno solo
4. **Cross-Encoder Reranking** - `mmarco-mMiniLMv2` reordena los top resultados por relevancia semántica
5. **Graph Boost** - Normas conectadas al concepto buscado suben en ranking (2.0x si definen, 1.3x si referencian)

Latencia: ~100ms por query. No requiere GPU en runtime.

## Grafo de Conocimiento

Grafo dirigido (NetworkX) construido sin LLM, usando regex sobre glosarios + referencias cruzadas entre normas.

```
131 nodos:  102 normas + 29 conceptos técnicos
238 aristas: 193 norma→norma (referencias) + 45 norma→concepto (define)
```

### Estructura jerárquica

```
LEY (ej: 20.936 - Ley de Transmisión)
  └── DECRETO reglamento_base (ej: D.62 "APRUEBA REGLAMENTO...")
        ├── DECRETO fija_valores (ej: D.61 "FIJA...")
        ├── DECRETO modifica (ej: D.44 "MODIFICA...")
        └── CONCEPTO definido en glosario (ej: COMA, VATT)
```

### Ejemplo: D.62 (Reglamento de Transferencias de Potencia)

```
                    ┌──────────────┐
       D.42(2020)───┤              ├───► DFL 4 (LGSE)
       D.44(2007)───┤   D.62       ├───► D.1 (Precios nudo)
       D.122(2019)──┤  (2006)      │
       D.33(2022)───┤  Reglamento  ├───► concepto:potencia firme
                    │   base       ├───► concepto:potencia inicial
                    │              ├───► concepto:balance de potencia
                    └──────────────┘
         ENTRA                          SALE
   (normas que lo citan)          (normas que cita + conceptos que define)
```

El nodo más conectado es **DFL 4 (LGSE)** con 40 conexiones — la ley madre del sector eléctrico.

### Extracción de conceptos

Los 29 conceptos provienen exclusivamente de **secciones de definiciones/glosarios** de 8 normas. No se extraen definiciones de texto libre para evitar ruido (un filtro anterior basado en regex libre producía ~70% de falsos positivos).

Normas con glosario:
- D.S. N°10 (2019): COMA, VATT, AVI, CDAT, CDBT, PEAT, PEBT, DOL, VI
- D.S. N°37 (2019): COMA, VATT, AVI, AEIR, EGPT, coordinador, expansión
- D.S. N°62 (2006): potencia firme, potencia inicial, balance de potencia
- D.S. N°20: CDAT, CDBT, CFHS, empresa suministradora, usuario
- D.S. N°1: PEAT, PEBT, EFACTAT, EFACTBT, MFAR, NSN, PNEP, PNPP
- D.S. N°2: PEAT, PEBT, EFACTAT, EFACTBT, MFAR, NSN, PNEP
- Otros: TAG, TAL

### Clasificación automática de normas

| Clase | Patrón en título | Significado |
|-------|-----------------|-------------|
| `reglamento_base` | APRUEBA REGLAMENTO... | Establece definiciones y reglas |
| `fija_valores` | FIJA... | Aplica valores numéricos |
| `modifica` | MODIFICA... | Modifica otra norma existente |
| `deroga` | DEROGA... | Elimina otra norma |

### Graph Boost en resultados

| Etiqueta | Significado | Boost |
|----------|-------------|-------|
| `define concepto` | Reglamento base que define el término en su glosario | 2.0x |
| `aplica concepto` | Decreto que fija valores para el concepto | 2.0x |
| `modifica definición` | Decreto que modifica la norma definitoria | 2.0x |
| `menciona concepto` | Otra norma que menciona el concepto | 2.0x |
| `referencia a definitoria` | Referencia indirecta a norma que define el concepto | 1.3x |

Cuando hay boost activo, solo se muestran normas boosteadas (se filtra el ruido).

## Datos

| Dato | Cantidad | Notas |
|------|----------|-------|
| Normas en dataset BCN | 2,031 | Total disponible |
| Normas con texto completo | 103 | Descargadas vía Playwright |
| Artículos extraídos | 2,147 | Parseados desde las 103 normas |
| Embeddings (768-dim) | 2,147 | FAISS index, ~6MB |
| Nodos en grafo | 131 | 102 normas + 29 conceptos |
| Aristas en grafo | 238 | 193 referencias + 45 define |

### Estructura de datos

```
data/
├── normas_completas/           # JSONs con texto completo por norma
│   ├── decretos/               #   decreto_10.json, decreto_62.json, ...
│   ├── leyes/                  #   ley_20936.json, ...
│   ├── dfl/                    #   dfl_4.json, ...
│   └── resoluciones/
├── articulos_extraidos.json    # 2,147 artículos parseados
├── search_index/               # FAISS index + metadata
│   ├── articles.faiss
│   ├── articles_metadata.pkl
│   └── index_info.json
├── norma_graph/                # Grafo persistido
│   ├── normas_graph.pkl
│   └── normas_graph.json
└── normas_estructuradas/       # Metadatos de normas (sin texto completo)
```

## Módulos

```
src/search/
├── hybrid_search.py        # Motor de búsqueda híbrida + GraphRAG
├── graph_builder.py         # Construcción del grafo de conocimiento
├── embedding_generator.py   # Generación de embeddings con FAISS
├── article_extractor.py     # Extracción de artículos desde JSONs
├── concept_extractor.py     # Extracción de conceptos
└── reranker.py              # Cross-encoder reranking

config/
└── alias_normas.json        # Alias informales + conceptos base manuales

scripts/
└── DOWNLOAD_ALL_NORMS.py    # Descarga masiva desde BCN
```

## Uso

### Setup

```bash
cd dark-data-scrapers/pagina_bcn
python3 -m venv venv
source venv/bin/activate
pip install sentence-transformers faiss-cpu rank-bm25 networkx torch
```

### Pipeline de indexación (una vez)

```bash
# 1. Extraer artículos de las normas descargadas
python3 -c "from src.search.article_extractor import ArticleExtractor; ArticleExtractor().run()"

# 2. Generar embeddings (GPU recomendado, batch-size 8 para 4GB VRAM)
python3 -c "from src.search.embedding_generator import EmbeddingGenerator; EmbeddingGenerator().run()"

# 3. Construir grafo de conocimiento
python3 -c "from src.search.graph_builder import NormaGraphBuilder; NormaGraphBuilder().build()"
```

### Búsqueda

```bash
python3 -c "
from src.search.hybrid_search import GraphEnhancedSearch
search = GraphEnhancedSearch()
search.search('COMA')
"
```

### Descarga masiva de normas

Ver [GUIA_DESCARGA_MASIVA.md](GUIA_DESCARGA_MASIVA.md) para descargar las 2,031 normas desde BCN.

## Roadmap

### Fase 1: Generación con LLM (siguiente paso)

Agregar capa de generación para responder preguntas en lenguaje natural:

```
Hoy:    "COMA" → lista de artículos relevantes
Futuro: "¿Qué es COMA y cómo se calcula?" → respuesta sintetizada con citas
```

Opciones:
- **Claude API** (Anthropic) - Mejor calidad, ~$0.001/query
- **AWS Bedrock** - Mismo Claude pero dentro del ecosistema AWS

### Fase 2: Profesionalización con AWS

Llevar el sistema a la nube para tenerlo como servicio accesible:

```
S3 (normas) → Bedrock Knowledge Base → Pinecone free tier → Claude Haiku
                                                               │
API Gateway ← Lambda ← ──────────────────────────────────────-─┘
     │
     ▼
https://tu-api.awsapprunner.com/search?q=COMA
```

Stack AWS:
- **S3** - Almacenamiento de normas ($0.01/mes)
- **Bedrock Knowledge Base** - Orquesta chunking, embeddings y retrieval
- **Pinecone free tier** - Vector store permanentemente gratis (2GB, suficiente)
- **Bedrock Claude Haiku** - Generación de respuestas (~$0.001/query)
- **Lambda + API Gateway** - API serverless (pay-per-use)

Costo estimado: ~$1-5/mes con uso esporádico, $0 si no se usa.

### Fase 3: Mejoras al grafo

- **Temporalidad**: Distinguir versiones vigentes vs derogadas
- **Granularidad por artículo**: Conectar artículos individuales en el grafo (no solo normas)
- **Más relaciones**: `deroga`, `complementa`, `implementa`
- **Community detection**: Detectar clusters temáticos automáticamente (transmisión, distribución, generación, tarifas)

### Fase 4: Cobertura

- Descargar las ~1,928 normas restantes (ver guía de descarga masiva)
- Extraer más conceptos de glosarios adicionales
- Ampliar alias informales en `config/alias_normas.json`

## Dependencias principales

- **sentence-transformers** - `multilingual-e5-base` (embeddings), `mmarco-mMiniLMv2` (reranker)
- **faiss-cpu** - Índice vectorial para búsqueda por similitud
- **rank-bm25** - Búsqueda léxica BM25
- **networkx** - Grafo de conocimiento
- **torch** - Inferencia de modelos (GPU recomendado para indexación)
- **playwright** - Scraping de normas desde BCN

## Hardware

- **GPU recomendado**: 4GB+ VRAM para generar embeddings (batch-size 8 con GTX 1650 4GB)
- **CPU viable**: Embeddings tardan ~10x más sin GPU
- **RAM**: 8GB+ sistema
- Búsqueda en runtime: ~100ms por query (no requiere GPU)
