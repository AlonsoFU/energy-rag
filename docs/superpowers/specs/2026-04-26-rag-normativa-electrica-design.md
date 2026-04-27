# RAG sobre Normativa Eléctrica Chilena — Diseño

**Fecha:** 2026-04-26
**Estado:** Diseño aprobado, pendiente plan de implementación
**Autor:** Alonso (con asistencia de Claude Code)
**Repositorio:** `energy-rag`

---

## 1. Contexto

El repo ya tiene un sistema de búsqueda híbrida (BM25 + FAISS + RRF + cross-encoder + GraphRAG) sobre 103 normas (de 2,031 disponibles en BCN), 2,147 artículos extraídos. Funciona bien para retrieval pero **no genera respuestas** y la arquitectura actual (FAISS + JSON + pickle) limita updates incrementales y migración.

Este documento define el diseño para:
1. Cerrar la pieza de generación de respuestas con LLM.
2. Reemplazar FAISS + rank-bm25 + JSON por un único stack relacional (Postgres + pgvector + tsvector).
3. Modelar correctamente las relaciones cruzadas entre normas/artículos/conceptos.
4. Permitir actualización incremental del corpus BCN (régimen normal).
5. Mantener arquitectura local-first con migración futura a AWS sin rewrites mayores.

## 2. Objetivos y no-objetivos

### Objetivos

- Local-first: corre en hardware del usuario (GTX 1080 8GB VRAM, 14GB RAM).
- $0/mes operación local; ~$1-5/mes en API de Claude (sin suscripción, pay-per-use).
- Cobertura completa de BCN para normativa eléctrica chilena (eventualmente 2,031 normas, ~500k artículos).
- Updates incrementales sin downtime ni rebuild completo.
- CLI primero; web UI futura sin reescribir el core.
- Citas verificables verbatim (anti-hallucination crítico para uso legal).
- Migrabilidad a AWS conservando el código de aplicación.

### No-objetivos

- Cobertura más allá de BCN (CNE, Coordinador, SEC, Diario Oficial) — anexo para v3.
- Versionamiento temporal de normas (vigente vs derogada en una fecha) — pendiente v3.
- Multiusuario / autenticación — fuera de alcance hasta que llegue web UI.
- Fine-tuning de modelos en español legal — overkill al volumen actual.

## 3. Decisiones de stack

### 3.1 Vector store: PostgreSQL + pgvector

| Decisión | Razón |
|----------|-------|
| Postgres + pgvector + tsvector | Una sola DB para vector, BM25 y metadata. Concurrencia, updates incrementales triviales, RDS-portable. Aguanta hasta ~5M vectores antes de necesitar Qdrant/Milvus (techo 5x el universo realista) |
| Postgres en local (no Docker en v1) | Setup más simple en Ubuntu 24.04. Containerizar es trivial cuando llegue web UI |
| Índice HNSW sobre `embedding` | Mejor recall a la escala del proyecto |
| `tsvector` GIN para BM25 | Reemplaza `rank-bm25`; sincronizado vía columna GENERATED |

### 3.2 Modelos (todos locales en GPU 8GB)

| Componente | Modelo | VRAM | Año | Razón |
|-----------|--------|------|-----|-------|
| Embedder | `Qwen3-Embedding-0.6B` (FP16) | ~1.2 GB | jul 2025 | Top MTEB multilingual a su tamaño. Apache 2.0 |
| Embedder candidato bake-off | `microsoft/harrier-oss-v1-0.6b` | ~1.2 GB | mar 2026 | Reclama SOTA en MTEB Multilingual v2. Comparar contra Qwen3 sobre queries reales chilenas antes de fijar |
| Reranker | `Qwen3-Reranker-0.6B` (bf16) | ~1.5 GB | 2025 | 65.80 MTEB-R, +15% sobre bge antiguo |

**Total simultáneo:** ~2.7 GB → cabe holgado en 8 GB GTX 1080.

### 3.3 LLM (vía API)

| Uso | Modelo | Cuándo |
|-----|--------|--------|
| Contextual Retrieval (indexar) | Claude Haiku 4.5 + prompt caching | One-shot al ingestar y por norma nueva |
| Query expansion (HyDE, multi-query, step-back) | Claude Haiku 4.5 | Solo branch complejo |
| Generación principal | Claude Sonnet 4.6 | Default todas las queries |
| Generación complejo | Claude Opus 4.7 (lanzado abr 2026) | Solo branch complejo / multi-norma |
| Provider abstraction | `litellm` | Permite swap a Bedrock/OpenAI sin tocar código |

**Decisión explícita:** no usar LLM local para generación. Llama 3.3 8B Q4 cabría (~5 GB) pero con caída de 30-40% en calidad para español legal técnico vs Claude — no vale el ahorro de $1-5/mes.

### 3.4 Pipeline de retrieval

Hybrid search clásico + GraphRAG personalizado + técnicas 2024-2025:

- **BM25** vía tsvector
- **Vector** vía pgvector HNSW
- **RRF fusion**
- **Cross-encoder rerank**
- **Graph boost** (norma definitoria > aplicadora > mencionante)
- **Hierarchical chunking** (recupera fragmento, genera con artículo padre completo)
- **Contextual Retrieval** (Anthropic, 2024-09): chunk + 50-100 tokens de contexto generado por LLM antes de embeber. ROI documentado: -67% fallas de retrieval combinado con reranker.
- **Adaptive RAG router** (TF-IDF + SVM): clasifica simple vs complejo en <5ms, ~70-80% va por simple. Reportado: -28% costo LLM, -35% latencia P50.
- **Branch complejo:** Step-back + HyDE + multi-query (3 calls Haiku para enriquecer la query antes de buscar).

### 3.5 Generación con grounding

- **Entity Grounding obligatorio**: cada cita "Art. X de norma Y" se verifica verbatim contra el texto recuperado. Si falla → regenera 1 vez con prompt corregido. Si vuelve a fallar → respuesta marcada como `grounding_pass=false` con warning visible.
- Justificación: Lexis+ AI y Westlaw AI alucinan 17-33% incluso con RAG (Stanford 2025). Para uso legal, sin grounding hay riesgo real.

### 3.6 Frontend

- v1: CLI con Typer (`python -m src ask "..."`).
- Futuro: FastAPI + Streamlit. La RAG engine queda como módulo Python reusable; el frontend es una capa fina.

## 4. Esquema de base de datos

8 tablas + 2 vistas derivadas. Naming consistente en español, plural, todas las tablas mutables con `created_at`/`updated_at` mantenidas por trigger.

### 4.1 Resumen

| Tabla | Tipo | Filas full BCN |
|-------|------|----------------|
| `normas` | dominio (raíz) | ~2,031 |
| `articulos` | dominio (hijo de normas) | ~500,000 |
| `fragmentos` | dominio (chunks embebidos + tsvector + contextual) | ~1.5-2.5M |
| `conceptos` | catálogo de términos definidos | ~100-200 |
| `referencias` | grafo polimórfico (origen y destino flexibles) | ~5,000-50,000 |
| `consultas_log` | operacional (latencias, costos) | crece con uso |
| `descargas_estado` | operacional (BCN updater) | ~2,031 |
| `aliases_aprendidos` | operacional v2 (aliases sugeridos por LLM) | crece lento |

Vistas derivadas (compatibilidad con código existente del grafo):
- `norma_norma` → derivada de `referencias` filtrando edges entre normas
- `norma_concepto` → derivada de `referencias` filtrando edges norma↔concepto

### 4.2 SQL completo (resumen, ver migrations Alembic para versión final)

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Trigger genérico para updated_at
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- 1. NORMAS
CREATE TABLE normas (
    id_norma          TEXT PRIMARY KEY,
    tipo              TEXT NOT NULL,           -- LEY/DECRETO/DFL/RESOLUCION
    numero            TEXT NOT NULL,
    titulo            TEXT NOT NULL,
    fecha_publicacion DATE,
    organismo         TEXT,
    clase             TEXT,                    -- reglamento_base/fija_valores/modifica/deroga
    texto_completo    TEXT,
    metadata          JSONB,
    fetched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_normas_tipo_clase ON normas(tipo, clase);
CREATE INDEX idx_normas_fecha ON normas(fecha_publicacion DESC);
CREATE TRIGGER trg_normas_updated BEFORE UPDATE ON normas
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- 2. ARTICULOS
CREATE TABLE articulos (
    id          BIGSERIAL PRIMARY KEY,
    id_norma    TEXT NOT NULL REFERENCES normas(id_norma) ON DELETE CASCADE,
    numero      TEXT NOT NULL,
    titulo      TEXT,
    texto       TEXT NOT NULL,
    orden       INT,
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (id_norma, numero)
);
CREATE INDEX idx_articulos_norma ON articulos(id_norma);
CREATE TRIGGER trg_articulos_updated BEFORE UPDATE ON articulos
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- 3. FRAGMENTOS (lo que se embebe + busca)
CREATE TABLE fragmentos (
    id              BIGSERIAL PRIMARY KEY,
    articulo_id     BIGINT NOT NULL REFERENCES articulos(id) ON DELETE CASCADE,
    chunk_index     INT NOT NULL,
    text            TEXT NOT NULL,           -- chunk crudo
    contextual_text TEXT NOT NULL,           -- chunk + contexto Anthropic (lo que se embebe)
    embedding       vector(768),
    tsv             tsvector
                    GENERATED ALWAYS AS (to_tsvector('spanish', contextual_text)) STORED,
    token_count     INT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (articulo_id, chunk_index)
);
CREATE INDEX idx_fragmentos_embedding ON fragmentos USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_fragmentos_tsv       ON fragmentos USING gin  (tsv);
CREATE INDEX idx_fragmentos_articulo  ON fragmentos(articulo_id);
CREATE TRIGGER trg_fragmentos_updated BEFORE UPDATE ON fragmentos
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- 4. CONCEPTOS (glosarios)
CREATE TABLE conceptos (
    id          BIGSERIAL PRIMARY KEY,
    nombre      TEXT NOT NULL UNIQUE,
    definicion  TEXT,
    aliases     TEXT[],
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TRIGGER trg_conceptos_updated BEFORE UPDATE ON conceptos
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- 5. REFERENCIAS (grafo polimórfico)
CREATE TABLE referencias (
    id                  BIGSERIAL PRIMARY KEY,
    -- ORIGEN: XOR
    origen_articulo_id  BIGINT REFERENCES articulos(id)        ON DELETE CASCADE,
    origen_norma_id     TEXT   REFERENCES normas(id_norma)     ON DELETE CASCADE,
    -- DESTINO: XOR
    destino_articulo_id BIGINT REFERENCES articulos(id)        ON DELETE CASCADE,
    destino_norma_id    TEXT   REFERENCES normas(id_norma)     ON DELETE CASCADE,
    destino_concepto_id BIGINT REFERENCES conceptos(id)        ON DELETE CASCADE,
    --
    tipo_relacion       TEXT NOT NULL CHECK (tipo_relacion IN
                        ('cita','remite','aplica','modifica','deroga',
                         'complementa','define_termino','referencia_implicita')),
    confianza           REAL CHECK (confianza BETWEEN 0 AND 1),
    metodo_extraccion   TEXT NOT NULL CHECK (metodo_extraccion IN ('regex','llm','manual')),
    destino_subdivision TEXT,
    contexto            TEXT,
    metadata            JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((origen_articulo_id IS NOT NULL)::int +
           (origen_norma_id IS NOT NULL)::int = 1),
    CHECK ((destino_articulo_id IS NOT NULL)::int +
           (destino_norma_id IS NOT NULL)::int +
           (destino_concepto_id IS NOT NULL)::int = 1)
);
CREATE INDEX idx_ref_origen_art   ON referencias(origen_articulo_id);
CREATE INDEX idx_ref_origen_norm  ON referencias(origen_norma_id);
CREATE INDEX idx_ref_destino_art  ON referencias(destino_articulo_id);
CREATE INDEX idx_ref_destino_norm ON referencias(destino_norma_id);
CREATE INDEX idx_ref_destino_conc ON referencias(destino_concepto_id);

-- 6. CONSULTAS_LOG
CREATE TABLE consultas_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    query           TEXT NOT NULL,
    branch          TEXT NOT NULL CHECK (branch IN ('simple','complejo')),
    n_results       INT,
    latency_ms      INT,
    rerank_ms       INT,
    generation_ms   INT,
    llm_model       TEXT,
    llm_tokens_in   INT,
    llm_tokens_out  INT,
    grounding_pass  BOOLEAN,
    metadata        JSONB
);
CREATE INDEX idx_consultas_log_ts ON consultas_log(ts DESC);

-- 7. DESCARGAS_ESTADO (BCN updater)
CREATE TABLE descargas_estado (
    id_norma      TEXT PRIMARY KEY,
    estado        TEXT NOT NULL CHECK (estado IN ('pending','downloaded','failed','outdated')),
    intentos      INT NOT NULL DEFAULT 0,
    last_attempt  TIMESTAMPTZ,
    last_error    TEXT,
    bcn_hash      TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_descargas_estado ON descargas_estado(estado);
CREATE TRIGGER trg_descargas_updated BEFORE UPDATE ON descargas_estado
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- 8. ALIASES_APRENDIDOS (v2)
CREATE TABLE aliases_aprendidos (
    id              BIGSERIAL PRIMARY KEY,
    alias_text      TEXT NOT NULL,
    id_norma        TEXT NOT NULL REFERENCES normas(id_norma) ON DELETE CASCADE,
    confianza       REAL CHECK (confianza BETWEEN 0 AND 1),
    fuente          TEXT NOT NULL,           -- 'llm_extraction', 'manual_review'
    aprobado        BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (alias_text, id_norma)
);

-- VISTAS DERIVADAS
CREATE VIEW norma_norma AS
SELECT DISTINCT
    COALESCE(a1.id_norma, r.origen_norma_id) AS origen,
    COALESCE(a2.id_norma, r.destino_norma_id) AS destino,
    r.tipo_relacion
FROM referencias r
LEFT JOIN articulos a1 ON a1.id = r.origen_articulo_id
LEFT JOIN articulos a2 ON a2.id = r.destino_articulo_id
WHERE COALESCE(a2.id_norma, r.destino_norma_id) IS NOT NULL;

CREATE VIEW norma_concepto AS
SELECT DISTINCT
    COALESCE(a1.id_norma, r.origen_norma_id) AS id_norma,
    r.destino_concepto_id AS concepto_id,
    r.tipo_relacion AS relacion
FROM referencias r
LEFT JOIN articulos a1 ON a1.id = r.origen_articulo_id
WHERE r.destino_concepto_id IS NOT NULL;
```

### 4.3 Decisiones de schema explícitas

| Decisión | Razón |
|----------|-------|
| `vector(768)` no `halfvec(768)` desde el inicio | A 500k vectors son ~1.5GB FP32, cabe. Si RAM aprieta, swap es 1 ALTER COLUMN |
| Se embebe `contextual_text`, no `text` | Es la técnica de Anthropic — el chunk con contexto pegado adelante |
| `tsv` GENERATED automático | Postgres mantiene BM25 sincronizado en cada UPDATE |
| HNSW sobre IVFFlat | Mejor recall a la escala. IVFFlat solo gana >5M vectores |
| Grafo en SQL, no NetworkX, en runtime | Permite queries SQL para graph boost. NetworkX queda como herramienta de análisis offline |
| Tabla `referencias` polimórfica con XOR constraints | Cualquier entidad legal (norma, artículo) puede referenciar cualquier otra (norma, artículo, concepto). Es el modelo correcto del dominio |
| `descargas_estado.bcn_hash` | Detecta cambios silenciosos en BCN para re-ingestar |

### 4.4 Tamaño esperado

DB completa a full BCN (~500k artículos): **~6-8 GB** (vectores dominan).

## 5. Extracción de referencias

### 5.1 Patrones a detectar (8 categorías)

| # | Tipo | Ejemplo | Estrategia | Confianza |
|---|------|---------|------------|-----------|
| 1 | Norma con número | "D.S. N° 62", "Ley 20.936", "DFL 4" | Regex + lookup catálogo | 0.90 |
| 2 | Artículo de norma | "art. 5° del D.S. 62", "Arts. 5 al 8 del DFL 4" | Regex con grupos | 0.90 |
| 3 | Subdivisión | "letra b) del art. 5", "inciso 2° del Art. 12" | Regex captura subdivisión | 0.85 |
| 4 | Estructura jerárquica | "Título III, Capítulo 2 de la Ley 20.936" | Regex extendido | 0.80 |
| 5 | Alias/nombre conocido | "la LGSE", "Reglamento de Transferencias" | Lookup `config/alias_normas.json` | 0.85 |
| 6 | Auto-referencial | "el artículo precedente", "el siguiente" | Reglas posicionales (campo `articulos.orden`) | 0.70 |
| 7 | Por concepto definido | usa "COMA" definido en otra norma | Vía `referencias` con `destino_concepto_id` | 0.90 |
| 8 | Vaga | "el reglamento correspondiente", "la normativa vigente" | LLM Haiku con catálogo | 0.50-0.70 |

### 5.2 Pipeline de extracción

Estrategia híbrida regex + alias + posicional + (opcional) LLM. Por pasadas:

1. **Pasada 1 (regex):** patrones 1-4, ~55% recall
2. **Pasada 2 (aliases):** patrón 5 contra `config/alias_normas.json`, +15%
3. **Pasada 3 (posicionales):** patrón 6, +5%
4. **Pasada 4 (concepto-derivadas):** patrón 7, automático, +5%
5. **Pasada 5 (LLM, opcional v2):** patrón 8, +10-15%

**Cobertura:** v1 ~80% gratis, v2 ~90-95% por ~$1 one-time. Filtro previo limita LLM a fragmentos con vagueidad real (~12% del corpus).

**LLM siempre con prompt cached del catálogo + structured output JSON + threshold de confianza ≥ 0.7.** Devuelve también `razonamiento` para auditoría.

### 5.3 Catálogo de normas

Pieza central. Vive en RAM al arrancar, construido de 3 fuentes:

| Fuente | Contenido | Editado por |
|--------|-----------|-------------|
| Tabla `normas` | Variantes ortográficas auto-generadas (con/sin "N°", con/sin punto) | Sistema (BCN updater) |
| `config/alias_normas.json` (existente) | Aliases informales canónicos | Humano, commit a git |
| Tabla `aliases_aprendidos` | Aliases nuevos detectados por LLM, requieren aprobación | Sistema sugiere → humano aprueba → migra a JSON |

Estándar de la industria: datos como datos (JSON/DB), narrativa como docs (Markdown). El catálogo NO se documenta como Markdown source-of-truth.

## 6. Estructura de módulos Python

Estructura plana orientada a componentes (estándar comunidad RAG, vs Clean Architecture que era over-engineering para 1 dev).

```
src/
├── core/
│   ├── models.py                # Norma, Articulo, Fragmento, Concepto (pydantic)
│   ├── catalogo.py              # NormaEntry + Catalogo (in-memory lookup)
│   └── config.py                # pydantic-settings desde .env / settings.toml
├── components/                  # Piezas intercambiables (interfaces implícitas)
│   ├── vectorstore.py           # PostgresStore (BM25 + vector + grafo)
│   ├── embedder.py              # Qwen3Embedder
│   ├── reranker.py              # Qwen3Reranker
│   ├── llm.py                   # litellm wrapper (Claude por default)
│   └── chunker.py               # Hierarchical + Contextual Retrieval
├── pipelines/                   # Flujos end-to-end
│   ├── ingest.py                # extract → chunk → contextual → embed → upsert → refs
│   ├── retrieve.py              # router → BM25+vector+RRF+rerank+graph_boost+hierarchical
│   ├── generate.py              # expansion (HyDE/multi-query/step-back) + LLM + grounding
│   └── update.py                # BCN diff + descarga incremental + re-ingest delta
├── routing/
│   └── adaptive.py              # TF-IDF + SVM
├── extraction/
│   ├── regex_refs.py            # patrones 1-4
│   ├── alias_refs.py            # patrón 5
│   ├── positional_refs.py       # patrón 6
│   └── llm_refs.py              # patrón 8 (opcional v2)
├── eval/
│   ├── deepeval_runner.py
│   ├── legalbench_runner.py
│   └── domain_eval_runner.py    # eval set propio
├── cli.py                       # Typer
└── __main__.py
```

Mapeo desde el código actual:

| Archivo actual | Destino |
|----------------|---------|
| `src/search/hybrid_search.py` | split → `pipelines/retrieve.py` + `components/vectorstore.py` |
| `src/search/embedding_generator.py` | `components/embedder.py` (swap a Qwen3) |
| `src/search/reranker.py` | `components/reranker.py` (swap a Qwen3) |
| `src/search/article_extractor.py` | `pipelines/ingest.py` (mantener parsing, escribir a Postgres) |
| `src/search/concept_extractor.py` | parte de `pipelines/ingest.py` |
| `src/search/graph_builder.py` | `extraction/*.py` (split por tipo de patrón) |
| `scripts/DOWNLOAD_ALL_NORMS.py` | base de `pipelines/update.py`, mantener script legacy |

## 7. Flujos de datos

### 7.1 Ingestión inicial (one-shot)

```
JSONs en data/normas_completas/
  ↓ extract
normas + articulos en Postgres
  ↓ chunk hierarchical (400 tok, overlap 50)
fragmentos crudos
  ↓ Contextual Retrieval (Haiku 4.5 + caching, ~$5-15 one-time para 500k)
fragmentos con contextual_text
  ↓ Qwen3-Embedding-0.6B (GPU, batch 32, ~3-4h en GTX 1080 para 500k)
fragmentos con embedding + tsv
  ↓ concept extract (regex sobre glosarios)
conceptos
  ↓ reference extraction (5 pasadas)
referencias
  ↓
DB lista
```

Comando: `python -m src ingest`

### 7.2 Query (runtime)

1. **Adaptive router** (TF-IDF+SVM, <5ms) decide simple vs complejo.
2. **Branch SIMPLE** (~70% queries):
   - Embed query → BM25 + vector + RRF → rerank → graph boost → hierarchical expand → Sonnet 4.6 → grounding.
   - Latencia: ~1.5-2.5s. Costo: ~$0.01-0.03.
3. **Branch COMPLEJO** (~30%):
   - Step-back + HyDE + multi-query (3 calls Haiku) → retrieval ×5 → merge RRF → rerank → graph boost → hierarchical → Opus 4.7 → grounding más estricto.
   - Latencia: ~6-10s. Costo: ~$0.05-0.15.
4. **Entity Grounding obligatorio**: cita verbatim verificada o se rechaza/regenera.
5. **Log** en `consultas_log` con timing por etapa.

### 7.3 Update incremental (régimen normal)

1. Scrape índice BCN (1 request).
2. Diff vs `descargas_estado` → nuevas + outdated (por `bcn_hash`).
3. Descarga solo el delta (lógica existente de DOWNLOAD_ALL_NORMS).
4. Pipeline ingest sobre el delta.
5. Contextual Retrieval + embeddings solo sobre fragmentos nuevos (~$0.01-0.10 por norma).
6. Reconstruye edges afectadas.
7. Reporte stdout.

Cron sugerido: `0 3 * * *` (3am diario) o semanal.

Comando: `python -m src update [--dry-run]`

## 8. Errores, testing, observabilidad

### 8.1 Manejo de errores

Principio: **fail-soft en runtime, fail-loud en ingest.**

- Postgres conexión: retry 3x exponencial.
- Embedder/Reranker OOM: reduce batch_size y reintenta.
- Claude API: litellm hace retry con backoff. Si persiste → degrada (devuelve top-5 artículos sin LLM).
- BCN scraper bloqueado: pausa 1h, reintenta. Marca `failed` después de 3.
- Entity Grounding falla: regenera 1 vez. Si vuelve a fallar → respuesta marcada con warning.

### 8.2 Testing (3 niveles)

| Nivel | Herramienta | Frecuencia |
|-------|-------------|------------|
| Unit (puras: chunker, regex, RRF, normalización, alias resolution) | pytest | Cada PR |
| Integration con Postgres real | pytest + testcontainers | Cada PR |
| Eval (precision, recall, groundedness) | DeepEval + LegalBench-RAG-mini + eval set propio | Manual + CI semanal |

**Eval set propio del dominio** en `data/eval/queries_chilean_electric.jsonl` (50-100 queries con ground truth). Sin esto no hay medida real para el dominio.

### 8.3 Observabilidad

| Capa | Captura | Donde |
|------|---------|-------|
| Logs | Eventos discretos | stdout + `logs/app.log` rotando diario |
| Métricas | Latencias, contadores, grounding pass rate | tabla `consultas_log` |
| Comando `python -m src stats` | Dashboard ASCII en terminal | One-shot bajo demanda |

Alertas mínimas (log WARN/ERROR):
- `grounding pass rate < 85%` mensual → investigar.
- `p95 latencia SIMPLE > 200ms` → revisar índice/RAM.
- `costo API > $20/mes` → auditar volumen.
- `cita rechazada > 5% de queries` → bug en grounding o retrieval.

### 8.4 Backup

| Qué | Cómo | Cuándo |
|-----|------|--------|
| Postgres | `pg_dump` comprimido a `backups/YYYY-MM-DD.sql.gz` | Cron diario |
| JSONs originales BCN | Inmutable en `data/normas_completas/` | Source of truth |
| Modelos | Cache HuggingFace local (~3 GB) | Persistente |
| `config/alias_normas.json` + spec | Git | Cada cambio |

Tiempo de recuperación: 5 min restaurando dump, 3-4h re-ingestando from scratch.

## 9. Migración a AWS (futuro)

El diseño respeta interfaces de componentes para que el día que se migre, sea swap localizado:

| Interface | Local v1 | AWS futuro |
|-----------|----------|------------|
| `vectorstore` | `PostgresStore` local | `RDSStore` (mismo SQL, distinto host) o `OpenSearchStore` |
| `llm` | `LiteLLMProvider` → Claude API | `LiteLLMProvider` → Bedrock Claude (solo cambia config) |
| `embedder` | `Qwen3Embedder` GPU local | `BedrockEmbedder` o `vLLMEmbedder` en EC2 |
| `reranker` | `Qwen3Reranker` GPU local | `SagemakerReranker` |
| `frontend` | CLI/FastAPI local | API Gateway + Lambda |

Costo estimado AWS uso real: ~$15-40/mes con RDS db.t4g.medium + Lambda + APIs Claude. Solo se justifica con web UI activa multi-usuario.

## 10. Trabajo futuro (fuera de v1)

- **v2 — Reference extraction LLM:** patrón 8, +10-15% recall, ~$1 one-time.
- **v2 — Aliases aprendidos:** flujo de revisión humana sobre sugerencias del LLM.
- **v3 — Versionamiento temporal:** distinguir versiones vigentes vs derogadas en una fecha.
- **v3 — Cobertura más allá de BCN:** scrapers para CNE, Coordinador, SEC.
- **v3 — Web UI:** FastAPI + Streamlit sobre la misma RAG engine.
- **v4 — Fine-tuning:** Qwen3-Embedding fine-tuneado sobre pares query→artículo legal chileno (requiere ~1000 pares anotados).

## 11. Referencias

- Anthropic Contextual Retrieval (2024-09): <https://www.anthropic.com/news/contextual-retrieval>
- pgvector: <https://github.com/pgvector/pgvector>
- Qwen3-Embedding paper: <https://arxiv.org/abs/2506.05176>
- Microsoft Harrier-OSS-v1 (2026-03-30): <https://huggingface.co/microsoft/harrier-oss-v1-0.6b>
- jina-reranker-v3 (2025-09): <https://huggingface.co/jinaai/jina-reranker-v3>
- LegalBench-RAG: <https://arxiv.org/abs/2408.10343>
- Legal RAG hallucinations (Stanford 2025): <https://onlinelibrary.wiley.com/doi/full/10.1111/jels.12413>
- HalluGraph (2025-12): <https://arxiv.org/abs/2512.01659>
- MEL Spanish legal LM: <https://arxiv.org/abs/2501.16011>
- DeepEval: <https://github.com/confident-ai/deepeval>
- litellm: <https://github.com/BerriAI/litellm>
- eyecite (citation extraction reference): <https://github.com/freelawproject/eyecite>
