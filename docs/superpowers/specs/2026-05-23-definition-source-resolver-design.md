# Resolutor de fuente autoritativa de definiciones (skill) — Design Spec

Fecha: 2026-05-23 · Construye sobre B1 (`2026-05-23-authority-resolution-design.md`).
Bases legales verificadas en [[reference_chilean_norm_hierarchy]] y §3.

> **Qué es.** Un skill general que, para un concepto definido/mencionado en varias
> normas, elige el artículo que es la **definición autoritativa**. Generaliza el
> problema que destapó B1 (la marca `define_termino` apunta a una *etiqueta* de
> glosario, no al artículo donde el concepto se define de verdad — p.ej. SEC apunta
> a un glosario circular, no a la Ley 18410 que la crea).
>
> **Principio rector (regla de oro):** determinista por defecto. Para el residuo
> que la regla no resuelve, el criterio del LLM entra como **decisión tentativa**
> que **SÍ se aplica al glosario** (el sistema la usa de inmediato) pero queda
> **marcada `needs_review`** y listada en un lugar visible, para que el humano la
> revise y corrija. Nada se "cierra" en silencio: lo tentativo es reversible y
> siempre señalado. Todo —lo determinista y lo tentativo— se registra de forma
> auditable; lo tentativo además lleva bandera de revisión.

## 1. Problema

La arista `define_termino` de un concepto puede apuntar a una definición **floja**:
una *etiqueta* que sólo repite el nombre (`«Superintendencia»: la Superintendencia de
Electricidad y Combustibles`) o una remisión (`a que se refiere el art. X`), en vez del
artículo que realmente define el concepto. Resultado medido (B1, eval `alias_sigla`):
para nombres completos de instituciones el sistema —con razón— cita la **ley orgánica**
(SEC→Ley 18410/29819, CNE/Min→Ley 20402/1008692), que ni siquiera tiene arista
`define_termino`. Nuestro dato marca como "definición" algo que no lo es.

No se puede arreglar buscando "Créase…" (hay infinitas formas de definir/crear algo →
frágil). La generalidad debe venir de detectar la **debilidad** de la definición (genérica)
y de aplicar **criterios legales** de selección, no de reconocer la forma "buena".

## 2. Alcance y no-objetivos (YAGNI)

**En alcance:** elegir/mover la marca de la **definición autoritativa** de un concepto
entre artículos candidatos del corpus, con criterios deterministas + propuesta tentativa
auditada para el residuo.

**Fuera (otros frentes):**
- Derogación / vigencia (B2).
- UX de ambigüedad en tiempo de consulta (B3) — esto es ingesta/curación, offline.
- Reescribir el texto del glosario (es válido en su norma; sólo cambiamos a qué apunta
  la marca de "definición autoritativa").
- GraphRAG.

## 3. Bases legales (verificadas con fuente, 2026-05-23)

**Criterios de solución de antinomias (choques entre normas), ordenados:**
`jerárquico → cronológico (ley posterior) → especialidad (ley especial)`.
La jerarquía prevalece; el cronológico cede ante la jerarquía y a veces ante la
especialidad. **La doctrina reconoce explícitamente que estos criterios NO resuelven
todos los casos** — hay supuestos donde ninguno alcanza → ahí interpreta un humano.
Esto valida la arquitectura: regla primero; el residuo, propuesta + decisión humana.
Fuente: Henríquez, "Los jueces y la resolución de antinomias…", Estudios Constitucionales
(SciELO, 2013).

**Interpretación del texto:** Código Civil arts. 19–24 — tenor literal si el sentido es
claro (art. 19); palabras en su sentido natural y obvio (art. 20), técnico si aplica
(art. 21); contexto/sistematicidad (art. 22); y como último recurso espíritu general y
equidad (art. 24). Fuente: Código Civil de Chile, Título Preliminar §4.

**Jerarquía de rango (ya verificada en B1):** `LEY ≡ DFL ≡ DL > DECRETO/DS > RESOLUCIÓN`;
rango del **título**, no del `tipo`.

## 4. Arquitectura — tres capas

```
conceptos (con define_termino y/o candidatos por nombre)
        │
   ┌────▼─────────────────────────────────────────────┐
   │ CAPA 0 — Detector de sospecha (barato, genérico)  │  ¿la def marcada es floja?
   └────┬─────────────────────────────────────────────┘
        │ sospechoso → reúne candidatos (otros artículos que definen el concepto)
   ┌────▼─────────────────────────────────────────────┐
   │ CAPA 1 — Resolución determinista                  │  jerarquía→fecha→especialidad
   │   + descarta la def floja como autoritativa       │  + sustancia > etiqueta
   └────┬───────────────────────────┬──────────────────┘
   resuelto (ALTA confianza)        │ no resuelve (empate / nada sirve)
        │                      ┌────▼─────────────────────────────────┐
        │                      │ CAPA 2 — Decisión tentativa (LLM)     │  BAJA confianza
        │                      │   decide con fundamento; reversible   │
        │                      └────┬─────────────────────────────────┘
        ▼                           ▼
   aplica marca (alta)        aplica marca + flag needs_review (baja)
        └───────────── CAPA 3 — Registro auditable (TODO) ────────────┘
              (lo needs_review se lista aparte para tu revisión)
```

## 5. Capa 0 — Detección de sospecha (qué mirar, no la respuesta)

Señales **genéricas y neutrales al tema**. Sólo enrutan al resolutor; no concluyen nada
legal (por eso pueden usar medidas simples sin romper "nada fuzzy en lo legal"):

1. **Circular / etiqueta:** tras quitar el propio nombre del concepto, quedan pocas
   palabras de contenido (la def ≈ repite el nombre).
2. **Muy corta:** longitud de la definición por debajo de un umbral de sustancia.
3. **Remisión:** contiene patrón de reenvío (`a que se refiere`, `señalado en el art`,
   `definido en`, `en los términos de`) + una cita → apunta a la fuente real, no define.
4. **Desacuerdo entre fuentes:** el concepto tiene >1 candidato y difieren mucho en
   sustancia (uno largo, otros etiquetas) → las etiquetas quedan en duda.

Salida de la capa: por concepto, `suspect: bool` + qué señales dispararon.

## 6. Capa 1 — Resolución determinista

Entre los candidatos `{id_norma, articulo, rank, fecha, ámbito?, def_text}`:
1. **Descartar etiquetas** como autoritativas si existe al menos un candidato sustantivo
   (sustancia > etiqueta).
2. Sobre los sustantivos: **jerarquía** (reusa `derive_rank`) → **fecha** (lex posterior)
   → **especialidad** (si hay señal de ámbito; ver §10, hoy parcial).
3. Si queda **un único** ganador claro → `resolved` (**ALTA confianza**).
4. Si la regla no decide (empate sin criterio, o ningún candidato sustantivo en el set
   actual) → pasa a Capa 2.

Reusa y respeta el refinamiento de B1: rango que promueve una norma de posible otro
contexto (rango ≠ recencia) **no** auto-resuelve → va a Capa 2.

## 7. Capa 2 — Decisión tentativa (LLM local, baja confianza)

Sólo para el residuo. El LLM (Ollama, sin API paga) recibe los candidatos + el
nombre/aliases del concepto y **elige** el artículo más probable, **citando qué
criterio legal lo sustenta** (jerarquía/fecha/especialidad/sustancia) y, si corresponde,
señalando un artículo fuera del set de `define_termino` (p.ej. la ley orgánica). Política
(decisión del usuario):
- Devuelve `{id_norma, articulo, criterio, fundamento, confianza:"baja"}`.
- **SÍ se aplica** al glosario (apuntador `definition_source`) para que el sistema lo use
  de inmediato, pero con **`needs_review: true`** + el fundamento.
- Es **reversible** y queda **listado aparte** para revisión humana. No se "cierra" solo.
- Temperatura/seed fijos para reproducibilidad; pero la marca SIEMPRE va con `needs_review`.

## 8. Capa 3 — Confianza y registro auditable

**Confianza atada al criterio que disparó, NO un número inventado por el LLM:**
- `alta` = la decidió una regla determinista (Capa 1). → se aplica, sin bandera.
- `baja` = decisión del LLM (Capa 2). → **se aplica igual**, pero con `needs_review: true`.

Ambas escriben el apuntador `conceptos.metadata.definition_source = {id_norma, articulo,
criterio, confianza, needs_review}`. La diferencia es la **bandera**, no si se aplica.

**Registro (TODO, no sólo dudas):** `glossary/incoming/definition_source_review.yaml` con,
por concepto tocado: confianza, `needs_review`, artículo elegido, **criterio**,
**fundamento**, señales de sospecha y candidatos. Lo `needs_review: true` se lista
destacado para tu revisión; al confirmarlo, se limpia la bandera (idempotente).

## 9. Componentes (archivos) — el "skill"

| archivo | responsabilidad |
|---|---|
| `src/extraction/definition_quality.py` (NUEVO, puro) | Capa 0: `is_label(nombre, definicion)`, `is_remission(def)`, `substance_score(nombre, def)`, `suspect_definition(...) -> (bool, reasons)`. Sin DB. |
| `src/extraction/definition_source.py` (NUEVO, puro) | Capa 1: `resolve_definition_source(candidates) -> {status, id_norma?, articulo?, criterio?, confianza}`. Reusa `derive_rank`/`select_authoritative`. Descarta etiquetas; aplica jerarquía→fecha→(especialidad). |
| `src/extraction/definition_proposer.py` (NUEVO) | Capa 2: arma el prompt con los candidatos + criterios legales (§3), llama al LLM local (`get_llm_provider`), parsea `{id_norma,articulo,criterio,fundamento,confianza:"baja"}`. Aislado para poder testear con un LLM mock. |
| `scripts/resolve_definition_sources.py` (NUEVO, runner) | Orquesta capas 0→3 sobre todos los conceptos. `--apply` escribe el puntero `conceptos.metadata.definition_source={id_norma,articulo,criterio,confianza,needs_review}` (alta sin bandera; baja con `needs_review`); escribe el YAML de auditoría. Idempotente (`metadata.def_source_resolved`). Dry-run por defecto. |
| `src/pipelines/concept_injection.py` (MODIFICAR) | El inject prefiere `metadata.definition_source` (más específico que `authoritative` de B1) cuando existe — **incluida la baja confianza** (el sistema usa lo tentativo de inmediato; la bandera `needs_review` es para curación, no bloquea el uso). |
| `SKILL.md` del sub-proyecto (NUEVO, opcional) | Documenta el procedimiento del skill (capas, criterios, confianza) para reusarlo/ajustarlo a futuro. |

## 10. Especialidad / ámbito (parcial hoy, honesto)

La especialidad necesita saber el **ámbito** de cada norma (materia/organismo). Hoy no
está derivado (B-ámbito diferido). Mientras tanto, la Capa 1 usa especialidad sólo si hay
una señal barata disponible (clase/organismo de la norma vs el concepto); si no, ese
desempate cae a Capa 2 (propuesta). No se inventa ámbito.

## 11. Incrementalidad

Corre en la cadena de ingesta tras B1:
`extraer → build_definitions_auto → canonicalize_concepts (A) → resolve_authority (B1)
→ resolve_definition_sources (este) → [medir]`. Todo idempotente; normas nuevas
re-disparan la detección y, si aplica, una nueva propuesta a la cola.

## 12. Legal-safety

- Lo determinista (Capa 1) se aplica sin bandera y es trazable al criterio.
- El criterio del LLM **se aplica provisionalmente** pero SIEMPRE con `needs_review` +
  fundamento, **reversible** y **destacado** para revisión humana — nunca se presenta
  como definición confirmada ni se cierra en silencio (≈ exigencia legal de fundamentación
  y de revisión). Es un **apuntador de curación**, no contenido generado por el modelo.
- Detección de sospecha = sólo enruta, no concluye.
- Todo queda registrado y es auditable; lo tentativo, además, marcado.

## 13. Errores / edge cases

- Concepto sin candidatos sustantivos en el corpus → no se cambia la marca; se registra
  `needs_review` con "sin alternativa mejor".
- Definición floja PERO sin alternativa mejor → se conserva la actual, marcada
  `needs_review` ("débil, sin reemplazo"). No se rompe nada.
- LLM no disponible / salida no parseable → se omite la Capa 2; la marca actual se conserva
  y el concepto queda `needs_review` con las señales de sospecha (fail-open).
- Idempotencia: 2ª corrida no cambia lo de alta confianza ni re-marca lo ya confirmado
  (bandera limpiada). Lo `needs_review` sin confirmar se mantiene estable.

## 14. Tests

- `definition_quality`: etiqueta circular ("Superintendencia: la Superintendencia…") →
  suspect; remisión ("a que se refiere el art. 5") → suspect; def sustantiva ("persona
  jurídica de derecho público…") → no suspect.
- `definition_source`: dos candidatos (etiqueta vs sustantivo) → elige el sustantivo;
  dos sustantivos distinto rango mismo contexto → gana el mayor; rango≠recencia → no
  resuelve (pasa a Capa 2); un solo sustantivo → resolved alta confianza.
- `definition_proposer`: con LLM mock → devuelve `confianza:"baja"`; el runner aplica el
  puntero PERO con `needs_review: true`.
- Integración (DB): tras `--apply`, SEC/CNE/Ministerio tienen `definition_source` aplicado
  con `needs_review: true`, candidato a ley orgánica + fundamento; el YAML de auditoría los
  lista destacados con criterio y razón.

## 15. Diferido

- B-ámbito completo (derivar materia/organismo) para que la especialidad sea determinista.
- Flujo de confirmación masiva: revisar lo `needs_review` y limpiar banderas en lote.
- Crear aristas `define_termino` nuevas hacia leyes orgánicas (hoy sólo puntero en
  metadata; promover a arista es un paso posterior).
