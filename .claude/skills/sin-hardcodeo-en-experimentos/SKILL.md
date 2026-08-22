---
name: sin-hardcodeo-en-experimentos
description: Use BEFORE writing any hardcoded list, regex, keyword set, threshold table or if/elif chain that CLASSIFIES, DECIDES or ROUTES inside the Energy-RAG pipeline (intent detection, domain/off-topic gating, term extraction, entity disambiguation, document typing, ranking rules). Also use when an experiment is about to be measured against a set built from the same patterns the mechanism uses. The rule is not "never hardcode" - it is "hardcode LAST, never as the primary mechanism, and never silently".
---

# Sin hardcodeo en los experimentos

Regla del proyecto (decisión del usuario, 2026-08-17, reafirmada 2026-08-21):

> El hardcodeo **no es el mecanismo**. Es el **último recurso**, cuando la metodología
> ya no da más y hay que atajar casos específicos. Y cuando aparece, **no se pierde**:
> se guarda documentado, **fuera del pipeline**.

## La razón de fondo: el hardcodeo NO mejora el sistema, mejora el NÚMERO

Esto es lo que hay que entender antes que cualquier procedimiento.

Una regla escrita a mano **no le enseña nada al sistema**. Solo tapa los casos que el autor ya
vio. El modelo sigue igual de ciego frente al caso 51; lo único que cambió es que el eval —que
también salió de la cabeza del autor— ahora los cubre.

Por eso un experimento con hardcodeo **sube la métrica sin subir la capacidad**, y eso es peor
que no mejorar: te hace creer que el frente está cerrado y dejás de trabajarlo.

Los dos números del proyecto que lo prueban:

```
_DEF_INTENT   99.2% en el set primario   ->   dispara 0/64 con fraseos naturales
              el mecanismo no existia fuera de las 3 plantillas que el propio eval usaba

R6 filtro por longitud   quitaba 13 falsos positivos y costaba 16 aciertos
   intent_gate (logreg)  quito los 20 SIN perder ninguno
```

La regla no era una versión peor del clasificador: era **una cosa distinta que aparentaba
funcionar**. El clasificador generaliza a fraseos que nunca vio (52/64 con el test excluido del
train); la lista no generaliza a nada, por construcción.

**Corolario práctico:** si un cambio mejora la métrica y es una lista, la primera hipótesis no
es "mejoró el sistema" sino **"el eval y la lista comparten origen"**. Hay que probar lo
contrario antes de adoptarlo.

Por eso el hardcodeo va **al final**: cuando el mecanismo ya generaliza y quedan casos
residuales que ninguna generalización va a cubrir. Ahí atajarlos a mano es legítimo — es
cerrar la cola, no fabricar la curva.

## Por qué existe esta regla (costó un error real)

`_DEF_INTENT` era una lista hardcodeada (`qué es|definición de|qué significa`) que decidía si
una query pedía una definición. Falla **6 de 13** fraseos naturales. Peor: las **279 queries del
set primario usaban LAS MISMAS 3 plantillas del regex**, así que el eval se medía contra sí
mismo. El 99.2% reportado era sobre fraseos que el regex cubría por construcción.

Medido después (exp #41): con fraseos naturales el mecanismo dispara **0 de 64**.
El reemplazo por diccionario + clasificador (exp #43/#44) dio **+6, p=0.0312**.

## El test, antes de escribir la lista

Preguntá en este orden. Pasás al siguiente solo si el anterior falla:

1. **¿El dato ya existe en la base?**
   El término no se infiere: está en `fragmentos_definicion.termino`. La norma no se
   adivina: está en `normas`. El artículo no se deduce: está en `articulos`.
   → Un lookup contra una tabla **no es hardcodeo**, es usar el dato.

2. **¿Se puede aprender de ejemplos?**
   Clasificador sobre embeddings (logreg), medido con CV fuera de muestra.
   ⚠️ El coseno crudo **agrupa por tópico, no por intención** (exp #42: 1-NN 28.9%).
   La regresión logística sí separa **cuando hay suficientes ejemplos** (binario: 0.990 con
   295 positivos; multi-clase: 0.783 con ~14 por clase, exp #49 → no adoptado).

3. **¿Se puede derivar de la estructura?**
   Jerarquía normativa, fecha, grafo de citas, frecuencia en el corpus.

4. **Recién acá: regla explícita.** Y con las tres condiciones de abajo.

## Si igual hace falta la regla

**Las tres condiciones, sin excepción:**

- **FALLBACK, nunca primero.** El mecanismo corre antes; la regla solo actúa donde
  el mecanismo no opinó. Nunca al revés.
- **Flag-gated y medido.** Default OFF hasta tener el pareado. Si es flat, no entra.
- **Documentada en `docs/reglas-candidatas.md`.** Con el caso que la motivó, el número
  que la justifica, y qué mecanismo debería reemplazarla.

**Y si no cumple las tres: NO va al pipeline.** Va igual a `docs/reglas-candidatas.md`,
porque el hallazgo no se pierde — se guarda para cuando la metodología se agote.

## Dónde vive lo que NO entra al pipeline

`docs/reglas-candidatas.md` — el banco de reglas identificadas y **no aplicadas**.
Cada entrada: qué caso ataja · qué evidencia hay · por qué no está en el pipeline ·
qué la reemplazaría. Es material, no basura.

## Trampa aparte: el SET de evaluación

Un mecanismo sin hardcodeo medido con un set que **el autor escribió con los mismos patrones**
sigue siendo circular. Antes de creer un número:

- ¿Las queries de test usan fraseos que el mecanismo NO cubre por construcción?
- ¿El set de entrenamiento y el de test están **separados**? (`queries_fraseos_v1` se
  excluyó del train del gate, a propósito.)
- ¿Las queries las escribió alguien distinto del que construyó el sistema?
  → Si la respuesta es no, **el número se reporta con ese caveat**, no como generalización.

## Checklist antes de dar por bueno un experimento

- [ ] El mecanismo principal es dato, modelo o estructura — no una lista
- [ ] Toda regla que quedó es fallback, flag-gated y medida
- [ ] Las reglas descartadas están en `docs/reglas-candidatas.md`, no borradas
- [ ] El set de test no comparte plantillas con el mecanismo
- [ ] Train y test separados, y dicho explícitamente
- [ ] El caveat de autoría del set está en el reporte

## Señales de que estás por romper la regla

| Pensamiento | Realidad |
|---|---|
| "es solo una lista corta" | `_DEF_INTENT` eran 8 patrones y costó 0/64 de cobertura |
| "el regex acá es obvio" | lo era también para "qué es X"; falló 6 de 13 fraseos |
| "lo mido después" | el set con el que lo medirías probablemente ya está contaminado |
| "es extracción, no clasificación" | válido — pero decilo explícito y dejá que el DATO decida |
| "total es fallback" | verificá que corra DESPUÉS, no antes |
