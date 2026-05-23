# Desambiguación de nombres canónicos — Design Spec

Fecha: 2026-05-22 · Branch: `feat/fase0-correctness` (off main, post-merge PR #4)

> Sub-proyecto de **resolución de entidades** (sección A del roadmap GraphRAG).
> Esta iteración es **solo "raíz + medir"**: limpiar nombres de concepto
> truncados de forma determinista, y medir el residuo real. La resolución por
> autoridad (lex superior/posterior/specialis) y la UX de ambigüedad quedan
> **decididas pero diferidas** a la próxima iteración (ver §10).

---

## 1. Goal

Que cada concepto se guarde con su **nombre canónico completo** (no una palabra
suelta ambigua), derivándolo de forma **determinista y legal-safe** desde el
texto del glosario. Es un **paso permanente del pipeline de ingesta**: corre
sobre los conceptos actuales y sobre los de cada norma nueva.

## 2. Problema (con datos reales)

La extracción guardó algunos conceptos con un **nombre truncado a una palabra**,
cuando el término real es un sintagma más largo. Ejemplo verificado en DB:

```
glosario (texto crudo, norma 1146553 art 5):
  f. Comité: Comité de adjudicación y supervisión del o los estudios de
             valorización a que se refiere el inciso segundo del art 108°…
     └encabezado┘ └────────────── cuerpo de la definición ──────────────┘
```

El encabezado es "Comité" (bare) → se guardó así. El nombre real vive en el
cuerpo. Consecuencia: "qué es Comité" es **ambiguo** (colisiona con "Comité para
las Autorizaciones Sectoriales e Inversión" de otra norma), y el sistema cita /
responde la entidad equivocada.

**Alcance real medido** (dry-run `scripts/dryrun_canonical_names.py` sobre 334
conceptos): la mayoría de los 97 conceptos de una palabra son **términos
legítimos** (Acometida, Cliente, Biomasa) y NO deben tocarse. El truncamiento
re-enunciado afecta a ~6-7 conceptos hoy. El valor real es **a escala**: A
corre en cada norma nueva, así que el corpus en crecimiento es el caso de uso.

## 3. Algoritmo A (determinista)

Para cada concepto con `definicion`, comparar el inicio del **cuerpo** contra el
`nombre`. Comparación con normalización ortográfica (minúsculas + sin tildes),
pero el nombre canónico extraído es **verbatim del texto original** (no se
inventa ni se re-acentúa).

Tres resultados:

### 3.1 No-fire
La definición **no empieza** con el nombre (token-alineado, seguido de espacio)
→ el concepto ya es el término correcto. No se toca.
- `Cliente` → "Persona natural o jurídica…" → no-fire ✓
- `Riesgo` → "posibilidad de ocurrencia…" → no-fire ✓
- Siglas (`C.O.M.A.` → "Costo de Operación…") → no-fire ✓ (es problema de
  *aliases*, otro sub-proyecto).

### 3.2 Fire (extensión)
La definición empieza con el nombre **y lo extiende**. El canónico = span
verbatim desde el nombre hasta el **primer límite**:

| tipo de límite | regex (corta ANTES del match) | ejemplo |
|---|---|---|
| puntuación | `[.;:,]` | "Comisión Nacional de Energía‖." |
| cláusula relativa | `a que / al que / a (los\|las\|la) que / que se refiere / que establece / que fija / que indica / que se \w+ / en adelante / según / conforme` | "…de los estudios de valorización‖ a que se refiere…" |
| participio/verbo de predicado | `establecid[oa]s? / definid[oa]s? / constituid[oa]s? / conformad[oa]s? / integrad[oa]s? / denominad[oa]s? / contemplad[oa]s? / es / son / será(n) / consiste / corresponde / comprende / se entenderá` | "Panel de Expertos‖ establecido en…" |

`canonical = (nombre + texto_hasta_límite).strip().rstrip(" ,;:.")`.
La palabra suelta original pasa a **alias**.

### 3.3 Confianza
- **Alta (auto-aplica)**: hay límite y el sintagma extra está en rango
  `1 ≤ palabras_extra ≤ 8`. → `UPDATE conceptos`.
- **Baja (revisión)**: no se halla límite (capturaría parte de la definición),
  o `palabras_extra > 8` (ej. "Comité…valorización" = 10 → revisión), o el
  nombre canónico **ya existe** como otro concepto (sería *merge*, no rename).
  → `glossary/incoming/canonical_review.yaml`.

### 3.4 Idempotencia
Si `metadata->>'canonical_source'` ya está seteado, el concepto se saltea. Re-
correr el paso es seguro y no re-extiende en cascada.

## 4. Componentes y archivos

| archivo | responsabilidad |
|---|---|
| `src/extraction/canonical_names.py` (NUEVO) | `extract_canonical(nombre, definicion) -> (canonical\|None, confianza)`. Puro, sin DB. Constantes de límites. |
| `scripts/canonicalize_concepts.py` (NUEVO) | Corre A sobre la DB. `--apply` (default dry-run). Alta→UPDATE; baja/colisión→YAML. Idempotente. |
| `tests/extraction/test_canonical_names.py` (NUEVO) | Unit tests de la regla pura. |
| `scripts/dryrun_canonical_names.py` (YA EXISTE) | Reporte read-only de distribución (queda como herramienta de inspección). |

`extract_canonical` reemplaza la lógica del dry-run y este último la importa
(DRY: una sola fuente de verdad de la regla).

## 5. Cambios de datos (DB)

Sin migración de schema (las columnas existen). Por cada alta-confianza:
```sql
UPDATE conceptos
   SET nombre  = :canonical,
       aliases = (SELECT array_agg(DISTINCT x)
                    FROM unnest(coalesce(aliases,'{}') || :bare_name) x),
       metadata = coalesce(metadata,'{}'::jsonb) || jsonb_build_object(
                    'canonical_source','definition_opening',
                    'original_nombre', :bare_name,
                    'canonical_span',  :verbatim_span,
                    'confianza', 1.0,
                    'metodo', 'regex_def_opening')
 WHERE id = :id;
```
Las aristas `define_termino` y `cita` no cambian (apuntan al mismo artículo).

## 6. Cola de revisión

`glossary/incoming/canonical_review.yaml` (convención existente de
`glossary/incoming/`). Una entrada por candidato baja-confianza:
```yaml
- concepto_id: 123
  original_nombre: "Comité"
  canonical_propuesto: "Comité de adjudicación y supervisión de los estudios de valorización"
  motivo: "palabras_extra=10 (>8)"
  definicion_inicio: "Comité de adjudicación y supervisión del o los estudios…"
```
Un humano confirma/edita y luego se aplica (mecanismo de aplicación de la cola =
fuera de alcance de esta iteración; por ahora la cola es el entregable).

## 7. Integración con la ingesta

`canonicalize_concepts.py` corre **después** de `build_definitions_auto.py`
(que crea conceptos + `define_termino`). En el flujo de ingesta de una norma
nueva: `extraer → build_definitions_auto → canonicalize_concepts → [medir]`.
Idempotente, así que correrlo de más no daña.

## 8. Medición / aceptación

- **Aceptación de la regla**: los unit tests pasan; el dry-run sobre los 334
  actuales da exactamente los buckets esperados (6 high, 1 low "Comité", 327
  no-fire, 0 colisiones) — congelado como test de regresión del corpus actual.
- **Aceptación de impacto** (honesta, esperada baja): tras `--apply`, re-correr
  `score_correctness.py` sobre el A/B. **Expectativa explícita: el lift de citas
  es chico** porque los truncamientos "descriptivos" (Escenario, Coordinado) y
  las colisiones reales NO los resuelve esta iteración. El objetivo real es
  (1) higiene de nombres canónicos y (2) dimensionar el residuo para la próxima
  iteración (autoridad/conflicto).
- Sin regresión: off_corpus refusal sigue 100%.

## 9. Legal-safety

- Nombre canónico = **span verbatim** del texto del glosario (no inventado, no
  re-acentuado). Determinista; misma entrada → misma salida.
- Sin fuzzy, sin umbrales de similitud. Solo normalización ortográfica para
  comparar el prefijo.
- Alta confianza acotada (≤8 palabras, límite fuerte); todo lo demás a revisión
  humana. Ningún rename silencioso de baja confianza.

## 10. Decidido pero DIFERIDO (próxima iteración)

Estas decisiones ya se tomaron con el usuario; se implementan después de medir
el residuo de esta iteración:
- **Resolución por autoridad** ante un término definido en >1 norma: excluir
  derogadas/obsoletas → mayor rango (LEY > DECRETO > RESOLUCIÓN, *lex superior*,
  derivable de `normas.tipo`) → mismo ámbito (*lex specialis*) → fecha más
  reciente (*lex posterior*) → si sigue ambiguo, marcar conflicto.
- **UX de ambigüedad**: query con palabra suelta que matchea varios conceptos →
  **mostrar las opciones y pedir precisar** (no adivinar, no sesgar por
  posición).
- **Gating del chunk enfocado** (`inject_focused_definition`): aplicar solo
  cuando NO hay definición competidora en el pool; nunca forzar colisiones por
  posición (el estándar advierte contra sesgo posicional).
- **Truncamientos descriptivos** (def que describe en vez de re-enunciar el
  nombre, ej. "Escenario"): no detectables por A; van a la resolución de
  conflictos o a revisión manual.

## 11. No-objetivos (YAGNI)

- No resolver siglas/aliases acá (sub-proyecto aparte, Fase 1).
- No aplicar la cola de revisión automáticamente (la cola es el entregable).
- No tocar aristas ni re-chunkear.
- No LLM en esta iteración (A es determinista; C se reserva para el residuo).

## Fuentes

- Resolución de antinomias (lex superior/posterior/specialis): jurisprudencia
  clásica, aplicada como señales de ranking (no la computa el retriever).
- "An Ontology-Driven Graph RAG for Legal Norms" (arXiv 2505.00039v5):
  metadata de norma a tiempo de curación; resolución cross-norma = trabajo
  futuro abierto.
- "Towards Reliable Retrieval in RAG for Large Legal Datasets" (arXiv
  2510.06999): Document-Level Retrieval Mismatch + Summary-Augmented Chunking.
- "Correctness is not Faithfulness in RAG Attributions" (UvA, 2025): la cita
  correcta ≠ contenido correcto; verificar provenance.
