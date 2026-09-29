<h1 align="center">Energy-RAG</h1>

<p align="center">
  Recuperación de normativa eléctrica chilena con citas textuales verificadas.<br>
  Ejecución 100 % local: sin APIs de pago.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white">
  <img alt="Ollama" src="https://img.shields.io/badge/LLM-Ollama%20local-000000?logo=ollama&logoColor=white">
  <img alt="Estado" src="https://img.shields.io/badge/estado-uso%20interno-orange">
</p>

<p align="center">
  <img src="docs/sistema/pipeline.svg" alt="Pipeline de Energy-RAG" width="860">
</p>

---

## Contenido

- [Resumen](#resumen)
- [Resultados](#resultados)
- [Alcance y limitaciones](#alcance-y-limitaciones)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Uso](#uso)
- [Evaluación y reproducibilidad](#evaluación-y-reproducibilidad)
- [Actualización del corpus](#actualización-del-corpus)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Documentación](#documentación)
- [Hoja de ruta](#hoja-de-ruta)
- [Licencia y aviso legal](#licencia-y-aviso-legal)

## Resumen

Energy-RAG es un sistema de recuperación aumentada (RAG) sobre la normativa del sector eléctrico
chileno publicada por la Biblioteca del Congreso Nacional ([BCN LeyChile](https://www.bcn.cl/leychile)).
Dada una pregunta en castellano, devuelve **los artículos que la responden, con su texto**, y
opcionalmente un resumen redactado en el que **cada cita es un fragmento literal del artículo
citado**, verificado por coincidencia exacta.

| | |
|---|---|
| **Corpus** | 124 normas · 5.354 artículos · 6.611 fragmentos · 371 conceptos de glosario |
| **Búsqueda** | BM25 + vector denso (Qwen3-Embedding-4B) → RRF → reranker BGE-v2-m3 |
| **Redacción** | `qwen3:30b-a3b` vía Ollama, temperatura 0, citas textuales verificadas |
| **Almacenamiento** | PostgreSQL 16 + pgvector (HNSW sobre prefijo MRL de 1024 dimensiones) |
| **Actualización** | monitor semanal contra BCN con detección de cambios por hash estable |

## Resultados

Métrica principal del buscador: **recall@10**, proporción de preguntas en que el artículo correcto
aparece entre los 10 que se muestran. Medición del 2026-09-28.

| Conjunto de evaluación | n | recall@10 | Cita correcta |
|---|---:|---:|---:|
| Held-out (fraseo formal) | 64 | **100 %** (64) | 97 % (62) |
| Desarrollo (incluye 50 coloquiales) | 114 | **81 %** (92) | 73 % (83) |
| Preguntas reales, *gold* de terceros (SEC, CGE, Coordinador) | 16 | **81 %** (13) | 63 % (10) |

| Latencia por consulta | |
|---|---:|
| Modo buscador (`--buscar`) | 13 s |
| Con resumen redactado | ~79 s |

Los números no se escriben a mano: los genera [`scripts/estado.py`](scripts/estado.py). Detalle,
experimentos descartados y análisis de fallas en
[`docs/sistema/06-resultados-y-limites.md`](docs/sistema/06-resultados-y-limites.md).

## Alcance y limitaciones

**Uso previsto:** buscador interno operado por una persona que lee la fuente.

**Fuera de alcance:** responder de forma autónoma a terceros, o cualquier uso como asesoría legal.

Limitaciones conocidas:

- **Errores silenciosos.** El modo de falla típico es una cita textual de un artículo real que no es
  el que responde la pregunta: supera el verificador y casi nunca genera advertencia (en las
  preguntas reales, 5 de 6 errores salieron sin ella).
- **Preguntas coloquiales.** En el set de desarrollo, 18 de 31 fallas son de búsqueda: el artículo
  correcto nunca llega al top-10 cuando la pregunta no comparte vocabulario con la ley.
- **Redacción no bit-exacta.** Aun con temperatura 0, el modelo MoE puede variar el texto entre
  corridas idénticas; la búsqueda sí es determinista.
- **Muestra real pequeña.** 16 preguntas con *gold* de terceros (intervalo de confianza ~±22 puntos).

## Arquitectura

| Etapa | Componente | Detalle |
|---|---|---|
| 1. Léxica | BM25 sobre PostgreSQL (`tsv`) | pool de 50 candidatos |
| 2. Semántica | Qwen3-Embedding-4B vía Ollama (CPU) | pgvector, prefijo MRL de 1024 dim. + alias coloquial→legal |
| 3. Fusión | Reciprocal Rank Fusion | pesos según largo de la consulta; excluye derogados y duplicados |
| 4. Reordenamiento | BGE-reranker-v2-m3 | 30 → 10; CPU por defecto, GPU en modo buscador |
| 5. Refuerzos | deterministas, sin modelo | grafo de conceptos, glosario exacto, aviso de definiciones múltiples |
| 6. Redacción *(opcional)* | `qwen3:30b-a3b` | máx. 2 citas, cada una verificada como substring exacto del artículo |

Descripción completa en [`docs/sistema/01-arquitectura.md`](docs/sistema/01-arquitectura.md).

## Requisitos

| Recurso | Versión / mínimo |
|---|---|
| Python | 3.12 |
| PostgreSQL | 16 con extensión `pgvector` (el proyecto usa el contenedor `energy_rag_pg`) |
| Ollama | modelos `qwen3:30b-a3b` y `qwen3-embedding:4b` |
| GPU | 24 GB de VRAM (probado en RTX 3090; el LLM ocupa ~22 GB con contexto 32768) |
| RAM | 14 GB (el embedder corre en CPU para no desplazar al LLM) |

## Instalación

```bash
git clone https://github.com/AlonsoFU/energy-rag.git
cd energy-rag
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env                 # credenciales de Postgres y LLM_DEFAULT
docker start energy_rag_pg           # PostgreSQL 16 + pgvector
ollama pull qwen3:30b-a3b
ollama pull qwen3-embedding:4b
venv/bin/alembic upgrade head
```

## Uso

```bash
export PYTHONPATH=. HF_HUB_OFFLINE=1 HF_HOME=/ruta/a/cache/hf

# Modo buscador: artículos con su texto (~13 s)
venv/bin/python scripts/preguntar.py --buscar "¿me pueden cortar la luz si debo mes y medio?"

# Con resumen redactado y citas verificadas (~79 s)
venv/bin/python scripts/preguntar.py "¿me pueden cortar la luz si debo mes y medio?"

# Vistas derivadas del corpus
venv/bin/python scripts/preguntar.py --obligaciones coordinador
venv/bin/python scripts/preguntar.py --plazos

# Estado del sistema (corpus, configuración adoptada, métricas)
venv/bin/python -m scripts.estado
```

## Evaluación y reproducibilidad

Toda modificación se mide contra criterios registrados **antes** de ejecutar, sobre un conjunto de
desarrollo y uno held-out, con comparación pareada (McNemar) y la huella del corpus (`db_huella`)
en cada resultado.

Para validar un refactor del buscador sin re-medir todo el sistema:

```bash
venv/bin/python -m scripts.red_golden --salida /tmp/nueva.json
venv/bin/python -m scripts.red_golden --comparar data/eval/redes/busqueda_base.json /tmp/nueva.json
# código de salida 1 si cambia una sola posición en cualquiera de las 194 preguntas
```

Protocolo, conjuntos y métricas: [`docs/sistema/04-evaluacion.md`](docs/sistema/04-evaluacion.md).

## Actualización del corpus

Un proceso programado (lunes 06:00) vuelve a descargar las normas del dominio desde BCN, detecta
cambios mediante un hash estable del texto y los aplica con salvaguardas: verificación de identidad
de la norma, rechazo de textos que se acortan más de un 10 % y control del número de artículos. Cada
cambio queda registrado con los artículos del corpus que citan la norma afectada.

Detalle en [`docs/sistema/03-actualizacion-bcn.md`](docs/sistema/03-actualizacion-bcn.md).

## Estructura del repositorio

```
energy-rag/
├── src/
│   ├── pipelines/         búsqueda (retrieve.py), redacción (generate.py), verificación de citas
│   ├── components/        almacenamiento vectorial, embedder, reranker, cliente LLM
│   ├── extraction/        definiciones, obligaciones, plazos, referencias
│   ├── parsers/           estructura del articulado y limpieza del formato BCN
│   ├── crawlers/          descarga desde BCN (Playwright)
│   └── core/              configuración: los valores por defecto son la configuración adoptada
├── scripts/               34 herramientas operativas + 10 tareas programadas (ver INDICE.md)
│   ├── experimentos/      experimentos concluidos, citados como evidencia
│   └── archivo/           herramientas de un solo uso ya ejecutadas
├── data/
│   ├── eval/              conjuntos de evaluación y red de regresión
│   └── ...                normas descargadas; data/archivo/ contiene datos sin uso vigente
├── docs/
│   ├── sistema/           documentación vigente, por tema
│   └── bitacora/          historial de decisiones y experimentos
├── tests/
└── alembic/               migraciones del esquema
```

## Documentación

| Documento | Contenido |
|---|---|
| [01 · Arquitectura](docs/sistema/01-arquitectura.md) | flujo completo de una consulta y configuración adoptada |
| [02 · Corpus y datos](docs/sistema/02-corpus-y-datos.md) | contenido de la base, defectos corregidos y cómo revertirlos |
| [03 · Actualización BCN](docs/sistema/03-actualizacion-bcn.md) | monitor semanal y sus salvaguardas |
| [04 · Evaluación](docs/sistema/04-evaluacion.md) | conjuntos, métricas y protocolo de medición |
| [05 · Operación](docs/sistema/05-operacion.md) | uso, cola de experimentos, cuidado de la GPU |
| [06 · Resultados y límites](docs/sistema/06-resultados-y-limites.md) | desempeño, experimentos descartados, trabajo futuro |

El historial de decisiones está en [`docs/bitacora/`](docs/bitacora/).

## Hoja de ruta

- [ ] Ajuste fino del embedder con pares pregunta coloquial → artículo y negativos difíciles.
- [ ] Ampliar las preguntas reales con *gold* de terceros de 16 a ~100.
- [ ] Alertas ante fallos del monitor, la cola de trabajos o la GPU.
- [ ] Reranker en GPU también en el modo con resumen.

## Licencia y aviso legal

El texto de las normas es de dominio público y proviene de BCN LeyChile. El código no tiene aún una
licencia definida.

**Este sistema no constituye asesoría legal.** Toda respuesta debe verificarse en la fuente oficial.
