# Spec — Pipeline de extracción automática (conceptos / aliases / vigencia)

Fecha: 2026-05-21 · Branch: feat/postgres-rag-v1

## Problema

La curación manual de aliases/conceptos overfittea a este corpus: mejora las
respuestas solo para los casos anotados, no generaliza a conceptos ni normas
nuevas. Hoy solo 46/286 conceptos (16%) tienen aliases, todos a mano.

**Objetivo**: un algoritmo que LEA los documentos y complete
aliases/conceptos/aristas automáticamente, con score de confianza, de modo
que al ingerir una norma nueva se autopueble sin trabajo manual.

## Restricción dura (todo el proyecto)

Dominio legal → solo hechos literales del texto. Sin fuzzy, sin umbrales de
similitud, sin inferencia silenciosa. Lo inferido (LLM) va flagged, no se
auto-aplica.

## Evidencia (estudio sobre 2664 artículos — `scripts/study_extraction_patterns.py`)

| patrón | cantidad | calidad |
|---|---|---|
| Glosarios reales (≥3 ítems) | 22 arts / 19 normas | — |
| `SIGLA: expansión` en glosario | 16 | gold |
| Forma-corta (`Comisión: Comisión Nacional…`) | 18 | gold |
| `en adelante X` (alias) | 32 (+35 temporales filtrados) | silver, ~25% ruido |
| `Nombre (SIGLA)` | 30 | silver, sigla limpia + chequeo iniciales |
| Verbos derogación/modif | 1170, solo 120 con ref resoluble | mayoría apunta fuera del corpus |

Conclusiones de la evidencia:
- Las fuentes gold son chicas (~34) pero de máxima precisión.
- `(SIGLA)` tiene chequeo de confianza **gratis**: letras de la sigla vs
  iniciales del nombre ("PMGD" ↔ **P**equeños **M**edios **G**eneración
  **D**istribuidos).
- `en adelante X` necesita guard de stopwords (captura "Sistemas", "Período").
- **Vigencia por derogación rinde poco**: casi todas las derogaciones son
  enmiendas a leyes externas al corpus. La fecha de publicación hace el
  trabajo en la práctica.

## Arquitectura

Pipeline por-norma, idempotente, corre en ingestión (y como backfill sobre el
corpus actual). Cada extractor es una unidad aislada que emite candidatos
`(tipo, valor, concepto_destino, confianza, fuente, evidencia)`.

```
norma → [E1 conceptos] → [E2 aliases] → [E3 aristas] → [E4 vigencia] → [loader]
                              │
              gold (1.0) ─────┼───── silver (0.8) ───── bronze (<0.7, LLM)
                              ▼
                  auto-aplica conf≥0.8 ; flag conf<0.8
```

### E1 — Extractor de conceptos (ya existe, se reusa)
`build_glossary_define_edges.py` parsea `letra. TÉRMINO: definición`. Sin
cambios.

### E2 — Extractor de aliases (NUEVO, foco de fase 1)
Tres detectores deterministas, cada uno emite candidatos con confianza:

1. **Glosario sigla:expansión** (gold, 1.0): en un ítem `TÉRMINO: def`, si
   TÉRMINO matchea forma de acrónimo (`A.V.I.`, `CNE`) → alias = TÉRMINO,
   concepto = el de la expansión. Hecho literal.
2. **Glosario forma-corta** (gold, 1.0): si TÉRMINO ⊂ inicio de su def
   (`Comisión: Comisión Nacional de Energía`) → TÉRMINO es alias corto.
3. **`Nombre (SIGLA)`** (silver→gold si verifica): captura nombre + sigla;
   **sube a gold si las letras de SIGLA = iniciales del nombre**. Si no
   verifica → silver flagged.
4. **`en adelante [e indistintamente] [«]X[»]`** (silver, 0.8): X es alias del
   sustantivo que precede. Guard: descartar si X es stopword, fecha, o >5
   palabras. Verbatim: X debe aparecer en el texto.

Cada alias se valida contra el concepto destino por match exact-normalizado
(reusa `normalize_for_match`). Sin match exacto → no se crea.

### E3 — Aristas define_termino (ya existe, se reusa)
Sin cambios.

### E4 — Vigencia (fase 2, alcance reducido por evidencia)
- Default: cuando un concepto se define en ≥2 normas nuestras, gana la de
  `fecha_publicacion` más reciente (ya implementado como tiebreak en
  `graph_boost`).
- Mejora: parsear `(Derógase|Modifícase|Reemplázase) … (ley|decreto) N° X` →
  resolver X a `id_norma` por (tipo, numero). Solo crea arista si la norma
  referida está en el corpus. Marca la definición vieja como no-vigente.
- Expectativa: pocas aristas relevantes; no bloquear fase 1 por esto.

### Modelo de confianza
Campo `confianza` (float 0-1) + `metodo_extraccion` + `contexto` (evidencia
textual) en `referencias`/`conceptos.metadata`. Ya existen esas columnas.

### Loader
`conf ≥ 0.8` → auto-aplica a DB. `conf < 0.8` → escribe a
`glossary/incoming/<norma>_auto.yaml` con `status: not_reviewed` para revisión
(reusa el flujo YAML existente).

## Alcance de esta entrega (fase 1)

SOLO E2 (extractor de aliases gold+silver) + loader auto para gold/silver
verificado. Es lo que alimenta el `inject_curated_definitions` ya medido y
sube la cobertura de aliases (46 → ~100 esperado). E4 (vigencia) y la parte
LLM (bronze) quedan documentadas para fase 2.

## Cómo se valida (anti-overfitting)

- El extractor NO mira el eval. Extrae de los documentos.
- Métrica de aceptación: ¿sube `recall+art` en `queries_balanced_v2.jsonl`
  (339q) **sin bajar** off_corpus refusal (100%)?
- Como los aliases salen del corpus (no del eval), el lift generaliza por
  construcción. El set de eval solo confirma que no rompimos nada.

## No-objetivos (YAGNI)

- No fuzzy matching, no embeddings para alias.
- No parsear derogaciones a leyes fuera del corpus.
- No re-arquitecturar el flujo YAML existente.
