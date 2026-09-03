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

---

## FASE 1.1b — `answer_doc_limit` como palanca de latencia (criterio fijado 2026-08-24, ANTES de correr)

Exp #54 cerró `self_consistency_n` (se queda n=3, 103 s). El objetivo de ≤45 s sigue abierto.
`answer_doc_limit` recorta cuántos documentos ve el GENERADOR; el retrieval no cambia.

**Se corre en dos tiempos, y el primero puede matar el segundo.**

**Paso 1 — sonda de latencia** (`scripts/exp_doclimit_sonda.py`, 12 queries, ~30 min).
Solo cronómetro, sin calidad.
```
si NINGUN doc_limit deja mediana <= 45 s  ->  answer_doc_limit NO es el camino.
                                             Se cierra, se documenta y se pasa a 1.3.
```
El pareado de calidad sobre las 114 operativas cuesta ~5 h de GPU. Gastarlas para descubrir
que el mejor valor llega a 70 s es tirar la tarde.

**Paso 2 — pareado de calidad**, solo si el paso 1 encontró un valor K con mediana ≤ 45 s:
```
adoptar answer_doc_limit=K si  cita_ok cae <= 3  Y  cita_limpia cae <= 2
```
`cita_limpia` va más estricta que en #54 **a propósito**. Ahí la trampa era ganar `cita_ok`
rociando citas; acá el mecanismo dice lo contrario — con menos documentos el modelo tiene
menos dónde dispersarse, así que la precisión debería **subir**. Si `cita_limpia` cae, el
mecanismo no está haciendo lo que dice hacer y el ahorro de tiempo no lo compensa.

⚠️ El riesgo simétrico ya está anotado en `config.py`: las queries cuyo gold cae en rank 5-9
se pierden por definición. El pareado lo mide directo.


### VEREDICTO 1.1b (2026-08-24) — frente CERRADO

El paso 1 mató al paso 2. Mejor valor `doc_limit=2`: mediana **125.9 s** contra objetivo 45 s.
El pareado de calidad **no se corrió** — aunque saliera flat, adoptarlo no cumpliría el
objetivo. ~5 h de GPU ahorradas por haber fijado el criterio antes.

El ahorro real es **10 %**, no el 30 % de exp #33: aquel se midió sin `self_consistency`.
Con `n=3` el tiempo lo domina decodificar 3 respuestas, no el prompt.

**La velocidad queda en vLLM / llama.cpp** (throughput de decodificación). Cuello: RAM 14 GB.
Ver exp #55.

---

## FASE 1.1c — `self_consistency` en PARALELO (criterio fijado 2026-08-24, ANTES de correr)

Exp #55 cerró `answer_doc_limit`: el tiempo lo domina **decodificar 3 respuestas**, no el prompt.
Pero esas 3 respuestas hoy salen de un `for i in range(n)` — **una espera a la anterior**.

Hipótesis mecánica: decodificar UNA secuencia deja la GPU limitada por ancho de banda de
memoria (medido: la 3090 nunca pasa de 230 W con este MoE). Un lote de 3 secuencias lee los
MISMOS pesos una vez y los usa para las tres, así que debería costar mucho menos que 3×.

⚠️ Riesgo simétrico: `OLLAMA_NUM_PARALLEL` multiplica el KV cache reservado. El modelo ya ocupa
20.5 GiB de 24; si 3 slots no caben, Ollama descarga capas a CPU y queda **mucho más lento**,
no más rápido. Por eso se mide antes de tocar la configuración.

**Paso 1 — sonda**: 1 request contra 3 concurrentes, mismo prompt.
```
si 3 concurrentes NO tardan menos de 2x lo que tarda 1  ->  no hay batching efectivo:
                                                            se cierra y queda solo vLLM.
```
**Paso 2 — pareado de calidad**, solo si el paso 1 da verde:
```
adoptar paralelo si  cita_ok cae <= 2  Y  cita_limpia cae <= 2  Y  mediana <= 45 s
```
La calidad **debería quedar idéntica** — es la misma decodificación con la misma temperatura,
solo que simultánea. Si `cita_limpia` se mueve fuerte, algo más cambió y hay que entenderlo
antes de adoptar, no después.


### VEREDICTO 1.1c (2026-08-24) — no se adopta

El batching **funciona** pero el remedio es peor: `OLLAMA_NUM_PARALLEL=3` reserva 3 KV caches,
empuja la VRAM a 23.97/24.58 GiB, desaloja parte del modelo y cada token pasa a costar el doble
(87 → 41 tok/s).

```
config vigente,  3 secuenciales : 13.8 s
NUM_PARALLEL=3,  3 concurrentes : 25.0 s   <- casi 2x mas lento
```

Acá el cuello es la **VRAM**, distinto del cuello de vLLM (RAM 14 GB). Ver exp #56.

---

## EXP #57 — corte de dominio 0.30 → 0.36 (criterio fijado 2026-08-27, ANTES de correr)

Cuatro normas claramente ajenas pasan el corte actual y entran al pool de retrieval:
```
0.315  LEY 19496   protección del consumidor
0.332  LEY 20720   insolvencia          ← 415 artículos
0.341  DECRETO 30  transporte
0.355  LEY 18045   mercado de valores
```
Un corte en 0.36 las saca y deja dentro la LEY 21667 (0.394), que sí es del dominio.

⚠️ También dejaría fuera la LEY 21711 (0.369, concesiones geotérmicas) — energía, pero no
claramente de la subgerencia de mercados.

**Criterio de adopción**, pareado sobre `queries_operativas_v1` (114q):
```
adoptar 0.36 si  cita_ok NO cae  Y  cita_limpia NO cae mas de 2
```
Se pide que `cita_ok` **no caiga nada**: sacar normas del pool sólo puede ayudar si esas normas
eran ruido. Si `cita_ok` baja, alguna de las cuatro estaba aportando y el corte se lleva algo
útil por delante — y entonces el problema no es el umbral sino el clasificador.

⚠️ El caso que ningún corte arregla: la LEY 19882 (política de personal) puntúa **0.411**, más
que la LEY 21667 que sí es del dominio. El puntaje por articulado no ordena bien en esa zona.
Este experimento mide si mover el umbral ayuda igual, no si lo resuelve.

---

## EXP #59 — clasificar dominio con LLM en vez de embedding (criterio fijado 2026-08-29)

Exp #57 dejó el diagnóstico: el puntaje por embedding **no ordena por materia**. Biocombustibles
(0.300) y matriz energética (0.301) puntúan más bajo que acuicultura (0.311) e insolvencia
(0.332). Ningún umbral arregla un orden ya mezclado.

Alternativa: que un LLM lea el articulado y decida si la norma regula el mercado eléctrico.

**Casos de control, fijados ANTES de correr.** Son los 9 donde el embedding ya se sabe que
falla o acierta por poco; el LLM tiene que resolverlos bien:
```
DENTRO   LEY 21499  biocombustibles solidos          (embedding 0.300, casi fuera)
DENTRO   LEY 20698  matriz energetica ERNC           (embedding 0.301, casi fuera)
DENTRO   LEY 21770  ley marco autorizaciones sect.   (embedding 0.331)
DENTRO   LEY 20897  franquicia solar termica         (embedding 0.358)
FUERA    LEY 20484  no pago tarifa transporte publico(embedding 0.303, DENTRO hoy)
FUERA    RESOLUCION 838  concesion de ACUICULTURA    (embedding 0.311, DENTRO hoy)
FUERA    LEY 20720  insolvencia                      (embedding 0.332, DENTRO hoy)
FUERA    LEY 20886  Codigo de Procedimiento Civil    (embedding 0.347, DENTRO hoy)
FUERA    LEY 18045  mercado de valores               (embedding 0.348, DENTRO hoy)
```
El embedding acierta **0 de 9** con el corte 0.30 vigente (las 4 de arriba entran por poco y
las 5 de abajo también entran, que es el error).

**Criterio de adopción:**
```
adoptar el clasificador LLM si acierta >= 8 de los 9 casos de control
```
Con menos de 8 no vale cambiar un mecanismo adoptado por otro que falla parecido.

⚠️ Los 9 casos los elegí yo, y son justo los casos difíciles — no una muestra representativa.
Esto mide si el LLM resuelve **lo que el embedding no puede**, no la exactitud global. Si pasa,
falta medir el efecto en retrieval con pareado antes de tocar el pipeline.

---

## EXP #63 — `ollama_think=True` contra los tipos que NO CIERRAN (criterio fijado 2026-09-01)

Exp #62 y el diagnóstico por tipos dejaron el cuadro: **6 de 12 preguntas no cierran**, y el
corte es nítido —cierra lo que sale de UNA fuente, no cierra lo que hay que sintetizar—.

```
CIERRAN                        NO CIERRAN
rule-recall       2/2          rule-application   0/1
null-rechazo      2/2          temporal-plazo     0/1
bridge-multihop   1/1          comparison-multi   0/2
temporal-vigencia 1/1          aggregation        0/1
                               interpretation     0/1
```
Los que fallan tardan 150-200 s: consumen el presupuesto entero deliberando.

**El diagnóstico ya estaba escrito en `config.py`**, y el flag existe apagado: con
`think=False` el modelo razona DENTRO del cuerpo de la respuesta porque no tiene otro lugar
donde pensar; con `think=True` Ollama devuelve el razonamiento en el campo `thinking` y deja
`response` limpio. `ollama_num_predict_think=6000` ya está calibrado (con 2000 el modelo se
queda sin tokens antes de responder).

⚠️ **think=True ya se midió antes (GEN8) y salió mixto**: precisión 0.66 vs 0.58 y +40
respuestas con todas las citas correctas, pero **perdía 16 golds, casi siempre por rechazar**.
Esa medición se hizo sobre el set viejo, que es casi todo `rule-recall` — el único tipo que hoy
funciona bien. La pregunta abierta es si lo que costaba en `rule-recall` lo gana en los tipos
que directamente no responden.

**Criterio de adopción:**
```
adoptar think=True si  los tipos que NO CIERRAN pasan a >= 4 de 6 usables
                   Y   rule-recall + null-rechazo NO pierden ninguno (siguen 4/4)
```
La segunda condición es la que protege lo que ya funciona: no sirve arreglar la síntesis si se
rompe la definición, que es el caso de uso más frecuente.

### RESULTADO #63 (2026-09-01) — think=True arregla los 6 tipos que no cerraban

```
                  think=OFF   think=ON
rule-application    0/1    ->   1/1
temporal-plazo      0/1    ->   1/1
comparison-multi    0/2    ->   2/2
aggregation         0/1    ->   1/1
interpretation      0/1    ->   1/1
                    0/6         6/6      criterio pedia >= 4
rule-recall         2/2    ->   2/2      intactos
null-rechazo        2/2    ->   2/2      intactos
```
Costo: 150-200 s → 162-377 s en los casos duros.

⚠️ **NO se adopta todavía.** GEN8 midió que `think=True` pierde 16 golds por rechazar en el set
grande de `rule-recall`; mis 2 preguntas de ese tipo no alcanzan para desmentirlo. Falta el
pareado sobre `queries_operativas_v1` (114q).

**Criterio para adoptar de verdad:**
```
adoptar think=True si  cita_ok cae <= 3  Y  cita_limpia NO cae
```
`cita_limpia` no puede caer: think=True existe justamente para que el modelo deje de rociar
citas mientras delibera, así que si la precisión no sube o se mantiene, no está haciendo lo que
promete.

### ESTADO #63 (2026-09-03) — el pareado se encoló con el script equivocado, se rehizo

`exp_selfcons_n1` togglea `self_consistency_n`, no `ollama_think`. Corrió ~6 h y devolvió una
repetición del exp #54 (`cita_ok` 66→66, `cita_limpia` 27→35, que es n=1 vs n=3). La evidencia
quedó guardada como `data/eval/results/selfcons_n1_repetido_mal_etiquetado`.

El pareado real es `scripts/exp_think_paired.py` (plan v8), y va con **held-out** para no
adoptar sobre un solo set:
```
dev       queries_operativas_v1  114q   corriendo desde 2026-09-03 18:35  (~8 h)
held-out  queries_fraseos_v1      64q   encolado detras                   (~4.5 h)
```
El criterio de arriba **no se toca** y el script imprime el veredicto solo.
Si dev y held-out discrepan, **NO se adopta**: manda el held-out.
