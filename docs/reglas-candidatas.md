# Reglas candidatas — hardcodeo identificado y NO aplicado

Banco de reglas específicas encontradas durante el trabajo. **No están en el pipeline.**
Se guardan porque el hallazgo es real y sirve cuando la metodología se agote — atajar casos
concretos al final es legítimo; hacerlo como mecanismo principal no.

Ver `.claude/skills/sin-hardcodeo-en-experimentos/SKILL.md`.

Formato de cada entrada: **qué ataja · evidencia · por qué no está en el pipeline · qué la
reemplazaría**.

---

## R1 — Materias fuera del dominio eléctrico

```python
AJENA = r"tránsito|transporte público|obras públicas|procesal penal|insolvencia|
         reemprendimiento|copropiedad|urbanismo|construcciones"
```
- **Qué ataja:** identificar las 15 normas del corpus que no son del dominio eléctrico
  (Ley de Tránsito, Código Procesal Penal, Concesiones de Obras Públicas…).
- **Evidencia:** la norma más citada del corpus es la **LEY 18290 (Tránsito) con 472 citas**,
  casi todas desde esas mismas normas ajenas. Sin separarlas, el reporte de frontera engaña.
- **Por qué no va al pipeline:** es una **decisión de dominio del usuario disfrazada de regex**.
  Qué materias entran al corpus es la decisión 0.2 (frontera), pendiente. Yo no puedo tomarla.
- **Qué la reemplazaría:** un archivo de configuración de frontera que el usuario edite, o
  clasificación por organismo emisor + materia declarada en `normas`.
- **Estado:** hoy vive en `scripts/resolver_citas_normas.py`, que es **análisis, no pipeline**
  — no afecta ninguna respuesta. Aceptable ahí; **no debe migrar** a retrieval.

## R2 — Fragmentos de interfaz de BCN

```python
_CHROME = r"ley historia de la|volver arriba|comparar versiones|imprimir|descargar|
           compartir|ingresar|registrarse|política de privacidad|…|loading"
```
- **Qué ataja:** que el hash del texto cambie porque BCN movió un botón.
- **Evidencia:** 13 de 25 normas re-bajadas acusaron `texto_modificado`; **todas cosméticas**.
  LEY 20410: única diferencia `' Ley Historia de la'`.
- **Por qué SÍ está en el pipeline (`src/pipelines/texto_hash.py`):** es **normalización de
  texto**, no clasificación. Nada decide con ella: solo limpia antes de comparar. El estándar
  (boilerplate removal) es exactamente esto.
- **Riesgo asumido:** si BCN cambia su interfaz, la lista envejece y vuelven los falsos
  positivos. **No falla en silencio** — se ve como un pico de eventos en el monitor.
- **Qué la reemplazaría:** diff estructural sobre el DOM del articulado en vez del `innerText`.

## R3 — Verbos modificatorios

```python
_VERBO_MODIFICATORIO = r"introdúcense|modifícase|agrégase|sustitúyese|reemplázase|
                        derógase|incorpórase|elimínase|intercálase|refúndese"
```
- **Qué ataja:** distinguir el articulado PROPIO de una ley modificatoria del que
  **transcribe** para insertar en otra norma.
- **Evidencia:** corpus completo **2391 propios · 299 transcritos**. Sin esto, LEY 20701
  aportaría 15 artículos de los cuales **14 son de la LGSE** → citas legalmente falsas
  (`[Art. 20 de LEY 20701]`).
- **Por qué SÍ está en el pipeline (`norm_structure_parser`):** es **parsing estructural** de
  una fórmula legislativa fija del derecho chileno, no una heurística de dominio. El estándar
  legal-NLP (LexNLP, Blackstone) hace exactamente esto con reglas.
- **Qué la reemplazaría:** nada mejor a la vista; la fórmula es canónica y estable.

## R4 — Encabezado de parte dispositiva

```python
DISPOSITIVO = r"\n\s*(DECRETO|RESUELVO|RESUELVE|ORDENO)\s*:?\s*\n"
```
- **Qué ataja:** ingerir decretos tarifarios sin articulado (precios de nudo, peajes),
  separando el preámbulo (Visto/Considerando) del contenido real.
- **Evidencia:** DECRETO 1 (precios de nudo) tiene **14.177 chars** de contenido dispositivo y
  **0 artículos** parseables. Sin esto el retrieval nunca lo alcanza.
- **Por qué SÍ está (`scripts/ingest_sin_articulado.py`):** parsing de estructura documental
  canónica, y es **ingesta, no decisión en runtime**.
- **Qué la reemplazaría:** un parser de decretos que entienda la estructura completa.

## R5 — `_DEF_INTENT` / `_DEF_PREFIX` — **MEDIDA Y SACADA DEL PIPELINE** (exp #51)

```python
_DEF_INTENT  = r"qué es|qué son|qué significa|qué se entiende por|definición de|…"
_DEF_PREFIX  = r"^(qué es|definición de|qué significa|…)\s+"
```
- **Qué ataja:** detectar queries de definición y extraer el concepto.
- **Evidencia en contra:** falla **6 de 13** fraseos naturales; dispara **0/64** en
  `queries_fraseos_v1`; y el set primario usaba **sus mismas 3 plantillas** → eval circular.
- **Medido (exp #51):** sobre las **46 queries donde el diccionario NO encuentra término**
  (`queries_sin_diccionario_v1.jsonl`), el fallback inyecta **0/46** — ni una sola vez.
```
cita_ok   OFF 44/46  ->  ON 43/46   [gano 0, perdio 1]  p=1.0000
inject    OFF  0/46  ->  ON  0/46
```
- **Por qué era inútil, y era predecible:** el regex y el diccionario **consultan la misma
  tabla** (`fragmentos_definicion.termino`). Si el diccionario no encuentra el término,
  `def_exact` tampoco va a resolver el concepto que extrae el regex. Redundante por
  construcción. La hipótesis de que "cubre términos fuera del glosario" (ej. "Mora") era
  falsa: si no está en el glosario, `def_exact` devuelve `None` por ambos caminos.
- **Estado:** `regex_fallback = False`. El código sigue en `retrieve.py` pero **no se
  ejecuta**. Queda acá documentado por si alguna vez el extractor deja de depender de esa tabla.

## R6 — Filtro de términos genéricos del glosario — **DESCARTADA**

```python
# min 2 palabras, o >=N caracteres
```
- **Qué atajaba:** que "Cliente", "Ley", "Comisión", "Coordinador" disparen la inyección en
  queries operativas.
- **Evidencia:** trade-off malo, medido —
  `min 1 palabra: 54/64 aciertos, 20/51 falsos positivos` ·
  `min 2 palabras: 38/64 aciertos, 7/51 falsos positivos`.
- **Por qué no va:** costaba 16 aciertos para quitar 13 falsos positivos.
- **Reemplazada por:** `intent_gate` (logreg), que dejó los falsos positivos en **0/51 y 0/19**
  sin perder aciertos (exp #43c). **Ejemplo de que el mecanismo ganó a la regla.**

## R7 — Higiene del glosario — identificada, sin aplicar

- **Qué ataja:** 284 de 743 entradas de `fragmentos_definicion` (**38%**) no son términos sino
  fórmulas de modificación ("Agrégase el siguiente inciso final").
- **Evidencia de que NO urge:** `glossary_lookup` devuelve basura en **0/64, 0/114 y 0/279**.
  Nadie pregunta "qué es Agrégase el siguiente inciso".
- **Por qué no se aplicó:** sin impacto medible hoy. **Es higiene para escala**: con más normas
  crecen las fórmulas y sube la chance de colisión.
- **Qué la reemplazaría:** marcar el tipo de entrada en la ingesta, en vez de filtrar después.

---

## Regla de oro

Si una entrada de este archivo empieza a aparecer en el pipeline **sin flag y sin número**,
está mal puesta. El orden es siempre: **dato → modelo → estructura → regla**, y la regla
llega última, medida y documentada.
