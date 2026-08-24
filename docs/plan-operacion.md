# Plan para dejarlo operativo

Objetivo: pasar de *"sistema que funciona en experimentos"* a *"sistema que la Subgerencia de
Mercados usa"*. No perfecto — **utilizable, medido y mantenible**, con mejora continua después.

Fecha: 2026-08-24.

---

## Dónde estamos, sin adornos

| | estado |
|---|---|
| Calidad de respuesta | `cita_ok` **87.5 %** con fraseos naturales · 100/114 en preguntas operativas |
| Corpus | 70 normas en dominio · 3266 artículos · 4328 fragmentos |
| Mapa de obligaciones | 989 obligaciones con sujeto, acción y plazo validados contra el texto |
| Monitor de cambios | construido y probado · **nunca activado en producción** |
| Descubrimiento retrospectivo | funciona (trajo la Ley 20.936) |
| Descubrimiento prospectivo | **no resuelto** — ver `descubrimiento-prospectivo.md` |
| Interfaz | **no existe** — todo se usa por scripts de Python |
| Latencia | **139 s de mediana**, p90 165 s, máx 218 s |

### Los tres bloqueantes reales
1. **139 s por respuesta.** Nadie espera 2,3 minutos. Bloquea cualquier uso interactivo.
2. **No hay forma de preguntar** sin abrir una terminal y escribir Python.
3. **El eval lo escribí yo.** El 87.5 % mide mi forma de preguntar, no la del equipo.

Todo lo demás es mejora; esos tres son condición de uso.

---

## FASE 1 — Que se pueda usar `~8 h`

### 1.1 Resolver latencia vs precisión `3 h · GPU`
`self_consistency_n=3` triplica la generación. Se midió que sube la precisión de cita
0.59 → 0.66, pero se midió **con el corpus viejo**.

```
medir pareado n=3 vs n=1 sobre queries_operativas_v1, corpus actual
```
**Criterio de decisión (fijado ANTES de correr, para no racionalizar el resultado):**
- si `cita_ok` cae ≤ 2 y `cita_limpia` cae ≤ 5 → **adoptar n=1** y ganar 3× de velocidad
- si cae más → quedarse en n=3 y buscar la velocidad en otro lado (vLLM, menos documentos)

**Aceptación de la fase:** mediana ≤ 45 s.

### 1.2 Interfaz mínima `3 h · sin GPU`
Una CLI y un endpoint HTTP local. **No** una aplicación web: eso es alcance de otra etapa.
```
preguntar "¿cada cuánto se calcula el balance de transferencias?"
obligaciones --sujeto coordinador
cambios --desde 2026-08-01
```
**Aceptación:** alguien del equipo puede preguntar sin escribir Python ni saber qué es un embedding.

### 1.3 Que no se caiga solo `2 h · sin GPU`
Hoy: si Postgres se apaga, todo falla con un stacktrace. Si Ollama no responde, igual.
```
reintento con espera · mensaje claro al usuario · arranque automático de Postgres
```
**Aceptación:** apagar Postgres a mitad de una consulta produce un mensaje entendible, no un
volcado de Python.

---

## FASE 2 — Que corra solo `~4 h`

### 2.1 Monitor en producción `1 h`
El cron está escrito (`scripts/monitor_run.sh`) y **nunca se instaló**. Correrlo una vez a mano,
verificar el informe, y recién ahí ponerlo semanal.
**Aceptación:** una pasada completa sin intervención, con informe legible.

### 2.2 Servicios que sobreviven un reinicio `1 h`
Postgres se cae solo (ya pasó). El límite de la GPU no persiste. El PC se colgó dos veces.
```
Postgres con restart=always · watchdog ya existe · verificación de arranque
```
**Aceptación:** reiniciar el equipo y que todo vuelva sin tocar nada.

### 2.3 Higiene del repositorio `2 h`
```
248 scripts en scripts/, la mayoría experimentos muertos
~55 commits locales sin subir
```
**Aceptación:** los scripts que se usan en operación están separados de los de experimentación,
y el trabajo está respaldado fuera de este equipo.

---

## FASE 3 — Validar con uso real `~6 h`

### 3.1 Preguntas reales del equipo `usuario · 30 min`
20-40 preguntas escritas como se preguntan de verdad, con modismos y errores.
**Es el único insumo que no se puede fabricar desde adentro**, y sin él el número que reportamos
seguirá siendo circular.

### 3.2 Medir contra esas preguntas `2 h · GPU`
El número honesto del sistema para el equipo. Puede ser peor que 87.5 % — eso es información,
no fracaso.

### 3.3 Reentrenar el clasificador con ellas `1 h`
```
PYTHONPATH=. venv/bin/python -m scripts.train_intent_gate
```
Un comando. Hoy los coeficientes cargan mi sesgo; con preguntas reales cargan el del equipo.

### 3.4 Cerrar la brecha que aparezca `3 h`
Lo que falle en 3.2 define el trabajo. No se planifica antes de tener el dato.

---

## FASE 4 — Mantenible `~4 h`

### 4.1 Manual de operación `2 h`
Qué hacer cuando: no responde · el monitor avisa un cambio · hay que agregar una norma · se
llena el disco. En pasos, no en prosa.

### 4.2 Conectar el foso con el monitor `2 h`
Hoy son dos sistemas separados. El campo `proceso` de `obligacion` está vacío. Agrupando las
obligaciones en procesos (IVTE, reliquidación, peajes) el monitor pasa de
*"cambió el Decreto 10"* a **"cambió el Decreto 10 → se ve afectado el cálculo mensual de
Ingresos Tarifarios que hace el Coordinador"**.

---

## Total

```
FASE 1  que se pueda usar     ~8 h   (3 h GPU)   <- bloqueante
FASE 2  que corra solo        ~4 h
FASE 3  validar con uso real  ~6 h   (2 h GPU)   <- necesita 30 min tuyos
FASE 4  mantenible            ~4 h
                              ~22 h
```

## Lo que NO entra en este plan

Se deja fuera a propósito, para que "operativo" llegue:
```
descubrimiento prospectivo   bloqueado por sitios que bloquean; se retoma después
crawler CNE / NTCO           4-6 h con riesgo alto
aplicación web               una CLI y un endpoint alcanzan para empezar
multi-usuario, permisos      no hay caso de uso todavía
G4 entity resolution         el eval es ciego, no se puede medir
```

## Método (no cambia)

```
dato -> modelo -> estructura -> regla
```
Todo cambio se mide pareado, ambos brazos en la misma sesión. El criterio de aceptación se fija
**antes** de correr. El piso de ruido medido del sistema es 6 % en aciertos y 30 % en precisión
de cita: cualquier diferencia menor a eso no es mejora, es ruido.

---

## Bitácora

### 2026-08-24 — FASE 1.1 lanzada
Criterio fijado **antes** de correr (`scripts/exp_selfcons_n1.py`, set `queries_operativas_v1`):
```
adoptar n=1 si   cita_ok cae <= 2   Y   cita_limpia cae <= 5
si no            quedarse en n=3 y buscar velocidad en otro lado
```
Baseline con n=3 y el corpus actual: `cita_ok` 100/114 · `cita_limpia` 61/114 · mediana 139 s.

### 2026-08-24 — FASE 1.1 RESUELTA: **se queda n=3** (exp #54)
```
             n=1        n=3
cita_ok      97/114     95/114     n=1 mejor (+2)
cita_limpia  49/114     61/114     n=1 CAE 12   -> rompe el criterio (permitía 5)
segundos       33 s      103 s
```
n=1 acierta más pero **rociando** (3.39 citas vs 2.42). El criterio previo evitó adoptarlo.
**La fase 1.1 no cumple su objetivo de ≤45 s.** Queda pendiente buscar velocidad en:
vLLM/llama.cpp con decodificación restringida, o `answer_doc_limit` (ya medido: calidad flat,
−30 % de tiempo).
