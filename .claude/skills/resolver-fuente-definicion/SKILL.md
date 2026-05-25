---
name: resolver-fuente-definicion
description: Use when deciding which article is the AUTHORITATIVE definition of a legal concept among several candidate norms/articles (Chilean electrical regulation). Resolves the hard/low-confidence cases the deterministic resolver could not settle. Portable across Claude Code and OpenCode; engine can be a local Ollama model.
---

# Resolver la fuente autoritativa de una definición

Procedimiento para elegir el artículo que **define de verdad** un concepto cuando
hay varios candidatos y la regla determinista no alcanzó. Produce una decisión
**tentativa, de baja confianza**, con fundamento, y **nunca cierra el caso**: la
marca queda `needs_review` para confirmación humana.

> Regla de oro: **determinista por defecto; criterio (este skill) solo para el
> residuo difícil; difuso para ENTENDER, exacto para RESPONDER (artículo curado);
> todo queda registrado para revisión.**

## Cuándo se activa

Solo para conceptos que el resolutor determinista NO resolvió con alta confianza:
- la definición marcada es **floja** (etiqueta circular / muy corta / remisión), y
- no hay un único candidato sustantivo claro por jerarquía+fecha del mismo contexto.

Si la regla determinista ya resolvió (un único candidato sustantivo, o jerarquía y
fecha coinciden en el mismo contexto) → **no usar este skill**, esa decisión es de
alta confianza y se aplica sola.

## Bases legales (verificadas — no inventar)

- **Criterios de antinomia, en orden:** jerárquico → cronológico (ley posterior) →
  especialidad (ley especial). Jerarquía: `LEY ≡ DFL ≡ DL > DECRETO/DS > RESOLUCIÓN`
  (rango del **título**, no del campo `tipo`, que está mal etiquetado). La doctrina
  reconoce que estos criterios **no resuelven todos los casos** → cuando no hay
  seguridad, **proponer tentativo y marcar para humano**, no cerrar.
- **Contexto manda sobre rango entre contextos distintos:** el mismo nombre en una
  norma de otra materia puede ser otro concepto → si el ganador por rango es de
  **otro ámbito** que los demás, NO auto-resolver → tentativo + revisión.
- **Fuente constitutiva:** para una institución, la norma autoritativa suele ser su
  **ley orgánica** (la que la crea), que puede no tener arista `define_termino`
  (su texto no dice "se entenderá por…"). Ej. verificados: SEC → Ley 18410
  (id 29819), Ministerio de Energía → Ley 20402 (id 1008692).
- Interpretación del texto: Código Civil arts. 19–24 (tenor literal si es claro;
  sentido natural/obvio; contexto; y como último recurso espíritu general/equidad).

## Procedimiento

1. **Reunir candidatos** para el concepto (nombre + aliases): artículos con arista
   `define_termino` Y artículos traídos por **búsqueda en el corpus** (para alcanzar
   la ley orgánica u otras fuentes sin arista). Marca cada candidato `curated` o
   `retrieved`. Lo `retrieved` es fuzzy → solo alimenta este criterio tentativo,
   nunca una resolución determinista de alta confianza.
2. **Descartar etiquetas:** un candidato cuya "definición" solo repite el nombre o
   remite a otro lado no es la fuente; prefiere el que dice **qué ES** el concepto.
3. **Aplicar criterios en orden** sobre los candidatos sustantivos: jerarquía →
   fecha → especialidad/ámbito. Para instituciones, preferir la **ley orgánica**
   ("Créase/Crea la/el <organismo>") aunque venga por retrieval.
4. **Decidir tentativo:** elegir un artículo y **justificar** con el criterio usado
   (jerarquía/fecha/especialidad/constitutiva/sustancia). Si no hay seguridad o dos
   candidatos de distinto contexto compiten → dejar sin elegir y marcar el conflicto.
5. **Salida (JSON):** `{"id_norma","articulo","criterio","fundamento","confianza":"baja"}`
   o `{"status":"sin-propuesta","motivo":...}`. SIEMPRE `confianza:"baja"` /
   `needs_review:true`. La elección debe estar **dentro de los candidatos** (no
   inventar normas/artículos).
6. **Registrar** la decisión y su fundamento en la cola de revisión
   (`glossary/incoming/definition_source_review.yaml`) para confirmación humana.

## No-objetivos / seguridad

- No cerrar el caso ni presentar la decisión como confirmada: es tentativa.
- No inventar normas, artículos ni contenido: solo elegir entre candidatos reales.
- No tocar vigencia/derogación (otro frente, B2); si una fuente pudiera estar
  derogada y no se puede verificar → marcarlo en el fundamento.
- Determinismo no requerido aquí (es tentativo + revisión humana), pero la
  justificación debe citar el criterio legal concreto.

## Implementación de referencia (código actual)

La versión automatizada en el pipeline es `src/extraction/definition_proposer.py`
(prompt-procedimiento a Ollama) + `definition_source.py` (capa determinista) +
`candidate_gather.py` (merge curated/retrieved) + runner
`scripts/resolve_definition_sources.py`. Este SKILL.md documenta el **procedimiento**
para que lo siga un agente (Claude Code u OpenCode+Ollama) cuando la curación se
hace asistida en vez de automática.
