# GraphRAG — Roadmap maestro (energy-rag)

Fecha: 2026-05-21 · Branch: feat/postgres-rag-v1

> Roadmap por fases hacia un GraphRAG bueno y útil para normativa eléctrica
> chilena. Cada fase es un sub-proyecto con su propio plan detallado (spec →
> plan → implementación). Grounded en el estándar verificado (Microsoft
> GraphRAG, ver `docs/handoff-2026-05-20.md` y fuentes citadas abajo).

## Goal

Sistema híbrido: retrieval vectorial+léxico (recall semántico) + grafo de
conocimiento (relaciones explícitas) + LLM (razonamiento), legal-safe.

## Principios transversales (aplican a TODA fase)

1. **Legal-safe primero**: nodos/aristas = hechos literales del texto.
   Determinista (regex) para lo explícito; LLM solo para lo implícito y
   SIEMPRE flagged (no auto-aplicado). Sin fuzzy.
2. **Confianza por item**: cada nodo/arista lleva `confianza` (1.0
   determinista, <0.8 inferido) + `metodo_extraccion` + `contexto`
   (evidencia textual).
3. **Vigencia**: ante 2+ definiciones del mismo concepto → derogación
   explícita gana; si no, fecha más reciente; si no, marca conflicto.
4. **No alucinar**: el LLM solo redacta sobre el subgrafo/docs recuperados;
   verifier de citas post-hoc obligatorio.
5. **Medir antes de invertir**: cada fase se acepta solo si mueve una
   métrica sobre un eval que NO se tocó al construir (anti-overfitting).

## Estado actual (verificado)

| componente | estado |
|---|---|
| Retrieval híbrido BM25 + pgvector + RRF | ✅ |
| Patrón híbrido (sin JSON-schema, verifier post-hoc) | ✅ |
| Nodos concepto (334) | ✅ |
| Aristas `define_termino` (222) + vigencia por fecha | ✅ |
| Inject definicional (local-GraphRAG mínimo) | ✅ |
| Aristas artículo→concepto "menciona" (`cita`, 4037) | ✅ pero ruidosas |
| Aristas **norma→norma** (modifica/deroga/cita) | ❌ 0 |
| Aristas **concepto→concepto** (relación) | ❌ 0 |
| Detección multi-concepto en query | ❌ |
| Traversal de grafo en query-time (local search) | ❌ |
| Community detection (Leiden) + summaries (global search) | ❌ |
| Query router (grafo vs vector) | ❌ |
| Aliases automáticos | 🟡 46/334, manual |
| Eval multi-hop | ❌ |

---

## FASE 0 — Consolidar la base (cerrar lo de esta sesión)

**Goal**: dejar commiteado y medido lo ya hecho.
- Commit: `build_definitions_auto.py`, inject por `define_termino`+vigencia,
  eval v3, spec, estudios.
- Implementar **chequeo automático de correctitud** (no proxy): para cada
  query in_domain, ¿la respuesta cita el artículo definidor esperado Y su
  texto contiene la definición del glosario? → cifra dura sobre las 273.
- **Aceptación**: cifra de correctitud documentada; off_corpus refusal 100%.
- **Esfuerzo**: bajo. **Depende de**: nada.

## FASE 1 — Aliases automáticos (extractor determinista)

**Goal**: subir cobertura de aliases (46→~100) leyendo el texto, no a mano.
- Detectores (ver spec 2026-05-21): glosario `SIGLA:expansión` (gold),
  forma-corta (gold), `Nombre (SIGLA)` con chequeo de iniciales (silver),
  `en adelante X` con guard de stopwords/temporal (silver).
- Loader: conf≥0.8 auto; <0.8 a `glossary/incoming/*.yaml` para revisión.
- **Consideración**: ayuda a usuarios reales (que escriben siglas/variantes),
  NO mueve el eval actual (queries usan nombre canónico). Medir con un eval
  de queries en forma-alias.
- **Aceptación**: +N aliases verificados verbatim; sin colisiones.
- **Esfuerzo**: medio. **Depende de**: Fase 0.

## FASE 2 — Aristas norma→norma (derogación / referencia)

**Goal**: construir el grafo entre leyes (la base de relacional legal).
- Parsear `(Derógase|Modifícase|Reemplázase|…) … (ley|decreto) N° X` →
  resolver X a `id_norma` por (tipo, numero). Crear arista
  `(norma A) --modifica/deroga--> (norma B)` solo si B está en el corpus.
- También `según el art Y de la ley Z` → arista de referencia.
- **Consideración (verificada en estudio)**: 1170 statements, pero la
  mayoría apunta a leyes FUERA del corpus → pocas aristas intra-corpus
  útiles. No sobre-invertir; rinde poco hasta ampliar el corpus.
- **Aceptación**: aristas norma→norma intra-corpus creadas + alimentan
  vigencia de conceptos.
- **Esfuerzo**: medio. **Depende de**: Fase 0.

## FASE 3 — Multi-concepto + traversal local (relacional)

**Goal**: responder "relación entre A y B" recorriendo el grafo.
- Detección multi-concepto: escanear la query contra el índice (en memoria,
  O(n_tokens)), encontrar TODOS los conceptos presentes.
- Local search: para los conceptos detectados, recuperar sus artículos
  definidores + las aristas que los conectan (define, cita, norma→norma) →
  inyectar ese subgrafo (acotado por el budget de contexto).
- **Consideración**: solo tan bueno como las aristas (Fases 1-2). Multi-hop
  real necesita aristas concepto→concepto (Fase 5).
- **Aceptación**: sube recall en un eval de queries relacionales (a crear).
- **Esfuerzo**: medio-alto. **Depende de**: Fases 1, 2.

## FASE 4 — Query router (grafo vs vector vs inject)

**Goal**: decidir por query qué mecanismo usar (el "router" que el estándar
señala como difícil pero necesario).
- Reglas deterministas primero: patrón definicional → inject; 2+ conceptos →
  traversal; resto → híbrido vectorial.
- **Consideración (verificada)**: agregar grafo a queries simples EMPEORA
  precisión y suma latencia → el router debe NO usar grafo cuando no toca.
- **Aceptación**: el router no degrada las queries simples (in_domain
  estable) y mejora las relacionales.
- **Esfuerzo**: medio. **Depende de**: Fase 3.

## FASE 5 — Aristas concepto→concepto (LLM-extraction verificada)

**Goal**: relaciones implícitas entre conceptos (las que el regex no ve).
- LLM lee el artículo y propone relaciones `(concepto A) --rel--> (concepto B)`;
  un **verificador determinista** confirma que ambos conceptos y la evidencia
  aparecen verbatim en el texto. Solo se acepta lo verificado; resto flagged.
- **Consideración**: es la parte riesgosa (alucinación). Confianza <0.8,
  nunca auto-aplicar sin verificación verbatim. Recién acá entra el LLM al
  build del grafo.
- **Aceptación**: aristas concepto→concepto con evidencia verbatim;
  precision medida sobre muestra.
- **Esfuerzo**: alto. **Depende de**: Fases 2, 3.

## FASE 6 — Global search (community detection + summaries)

**Goal**: responder preguntas globales/temáticas ("resumime toda la
normativa de transmisión").
- Leiden sobre el grafo → comunidades jerárquicas. LLM genera "community
  reports". Query global → busca sobre los resúmenes.
- **Consideración (verificada)**: regenerar los community summaries cuando
  cambia el corpus NO es barato (no es O(1)). Costo de mantenimiento alto
  con normas que llegan seguido. Evaluar si las preguntas reales lo
  justifican antes de construir.
- **Aceptación**: responde preguntas globales que hoy el vectorial falla.
- **Esfuerzo**: alto. **Depende de**: Fases 2, 5 (grafo rico).

## FASE 7 — Evaluación de grafo (multi-hop)

**Goal**: medir lo que las fases 3-6 prometen, sin auto-engaño.
- Set de queries relacionales/multi-hop con ground-truth de camino en el
  grafo, verificado a mano. Holdout que no se mira al construir.
- **Criterio de inversión (verificado)**: GraphRAG vale si recall@k <60% en
  multi-hop. Esta fase mide ese número para decidir cuánto invertir en 3-6.
- **Esfuerzo**: medio (trabajo manual). **Depende de**: Fase 3.

---

## Orden recomendado

```
Fase 0 (cerrar) → Fase 7-mini (medir si hay queries multi-hop reales)
                        │
        ┌───────────────┴─── si multi-hop importa ──────────────┐
        ▼                                                         ▼
  Fase 1 (aliases)                                    Fase 2 (norma→norma)
        │                                                         │
        └──────────────► Fase 3 (multi-concepto+traversal) ◄──────┘
                                    │
                          Fase 4 (router)
                                    │
                    Fase 5 (concepto→concepto LLM)
                                    │
                          Fase 6 (global search)
```

**Decisión clave antes de invertir en 3-6**: medir (Fase 7-mini) si las
preguntas reales de los usuarios son relacionales/multi-hop. Si son mayormente
definicionales (como el eval actual), el ROI de GraphRAG-relacional es bajo y
conviene quedarse en Fases 0-1. Si hay multi-hop real (recall<60%), el grafo
es la inversión correcta (estándar: 86% vs 32% vector).

## Revisión 2 (2026-05-21) — componentes que faltaban del estándar

Tras investigar, 4 piezas que el estándar considera y el roadmap no cubría:

### A. Resolución/desambiguación de entidades (CRÍTICO — elevado)
GraphRAG por defecto asume "**mismo nombre = misma entidad**" — y eso es
citado como **causa raíz de fallos** en grafos reales ("GraphRAG looks great
until entity resolution breaks"). **Nosotros tenemos exactamente ese problema**:
"Cliente" está definido en Decreto 3386 (1935) y en decretos modernos. Hoy lo
tratamos como UN concepto y vigencia elige el reciente — pero puede ser que
sean **conceptos distintos** que comparten nombre (mismo término, contexto
regulatorio diferente).
- **Regla de resolución DECIDIDA (usuario, 2026-05-21)** — para elegir la
  definición autoritativa de un término definido en varias normas:
  1. **Excluir derogadas/obsoletas** (requiere aristas deroga de Fase 2 +
     estado de vigencia de la norma).
  2. **Preferir mismo ámbito** que el contexto de la query (ámbito derivable
     de `clase`/`organismo`/dominio de la norma; ej. eléctrico vs tránsito).
  3. **Desempatar por fecha** más reciente entre las que quedan.
  4. Si sigue ambiguo → **marcar conflicto**, no adivinar.
- Implicación: la resolución NO es solo fecha (lo de hoy) — primero filtra
  por vigencia y ámbito. Depende de Fase 2 (para saber qué está derogado) y
  de un campo de ámbito por norma.
- Técnicas estándar de apoyo: desambiguación contextual (vecinos del grafo),
  cross-document entity linking.
- **Ubicación**: precede a Fase 3 (sin resolución correcta, el traversal
  conecta nodos equivocados).

### B. Indexación incremental (cross-cutting)
Cuando llega una norma nueva: re-extraer entidades, **re-evaluar si fusionan
con entidades existentes** (resolución), y regenerar community reports
afectados. El estándar admite que hoy esto es "clunky". Para nosotros: definir
qué re-corre al ingerir una norma (extractor → resolución → vigencia →
[si Fase 6] summaries). Aristas/nodos nuevos son baratos; los summaries no.

### C. Almacenamiento y traversal del grafo (decisión explícita)
El estándar usa Neo4j (Cypher) para traversal + pgvector para vectores.
**Nosotros: quedarnos en Postgres** — traversal con **recursive CTE** (válido
a nuestra escala: cientos de normas, miles de aristas). Migrar a Apache AGE
(grafo en Postgres con Cypher) o Neo4j SOLO si el traversal se vuelve cuello.
No introducir un motor nuevo sin necesidad medida.

### D. Fusión vector + grafo (distinto del router)
El router decide QUÉ mecanismo; la **fusión** decide CÓMO combinar resultados
cuando se usan ambos. Patrón estándar (HybridCypherRetriever): vector trae
candidatos semánticos → se identifican sus nodos → traversal del grafo agrega
contexto conectado → se fusiona. Especificar la fusión como parte de Fase 4.

### E. Covariates / claims (YAGNI por ahora)
GraphRAG extrae "claims" sobre entidades con estado TRUE/FALSE/SUSPECTED. Para
legal sería útil (ej. "este artículo está vigente/derogado"), pero es avanzado.
No construir hasta tener el grafo base + evidencia de necesidad.

## Estado y orden de ejecución (consolidado 2026-05-23)

Backlog ordenado. Cada item gateado por medición. **GraphRAG (Fases 3-6) sigue
preservado abajo** como inversión grande del final, condicionada a medir queries
multi-hop reales.

| iter | qué | estado | doc |
|---|---|---|---|
| Fase 0 | correctitud dura (strict 85.7%) | ✅ hecho | handoff 2026-05-22 |
| **A** | nombres canónicos (6 renames, idempotente, ingesta) | ✅ **hecho+aplicado** | specs/plans 2026-05-22-canonical-* |
| fix | alias-aware (acrónimos: alias_sigla 78→97% / 63→95%) | ✅ **hecho** | handoff 2026-05-23b |
| **B1** | resolución de autoridad (rango→fecha→flag) + corrige gold del eval | 📋 **spec+plan listos, NO ejecutado** | specs/plans 2026-05-23-authority-resolution |
| B-ámbito | lex specialis (desempate por dominio) | ⏳ diferido (corpus casi todo energía) | — |
| B2 | derogación/vigencia (BCN obtxml + parse 175 "Reemplázase" + flag tácitas) | ⏳ diferido (mayoría fuera del corpus, bajo ROI) | Exp T / Fase 2 abajo |
| B3 | UX de ambigüedad (mostrar opciones + pedir precisar) | ⏳ diferido | — |
| C | gating del chunk enfocado (focused solo sin competidor) | ⏳ flag dormido, pendiente gating | config inject_focused_definition |
| D | aliases/siglas automáticos | ⏳ 46 manuales | Fase 1 abajo |
| E | truncamientos "descriptivos" (Escenario) → C-LLM verbatim o revisión | ⏳ diferido | — |
| F | aplicar la cola de revisión `glossary/incoming/canonical_review.yaml` | ⏳ pendiente | — |
| G | **GraphRAG relacional** (Fases 3-6 abajo) | ⏳ diferido, "sí o sí más adelante" | este doc |

**Orden recomendado:** B1 (lever de citas + arregla el eval) → C (focused gating)
→ D (aliases) → medir distribución real de preguntas → si hay multi-hop, GraphRAG.

**Hallazgo transversal clave:** el ground-truth del eval es **ingenuo de autoridad**
(espera glosarios-decreto cuando lo correcto es la Ley) → B1 lo corrige.

## No-objetivos (YAGNI)

- No construir community summaries (Fase 6) sin evidencia de preguntas globales.
- No LLM-extraction (Fase 5) hasta tener verificador verbatim.
- No aristas a normas fuera del corpus.

## Fuentes (verificadas 2026-05-21)

- Microsoft GraphRAG — local/global search, Leiden, community reports:
  https://microsoft.github.io/graphrag/
- From Local to Global (paper):
  https://www.microsoft.com/en-us/research/publication/from-local-to-global-a-graph-rag-approach-to-query-focused-summarization/
- GraphRAG vs Vector RAG (86% vs 32% multi-hop, cuándo usar, "legal clause
  dependencies"): https://tianpan.co/blog/2026-04-19-graphrag-vs-vector-rag-architecture-decision
- DRIFT search: https://www.microsoft.com/en-us/research/blog/introducing-drift-search-combining-global-and-local-search-methods-to-improve-quality-and-efficiency/
