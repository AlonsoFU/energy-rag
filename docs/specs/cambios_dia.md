# Spec — informe diario de cambios normativos (`cambios_dia`)

Estado: **borrador para revisión** · 2026-10-06 · sin código escrito todavía.

## 1. Objetivo

Que cada día a las 08:00 exista un informe local que diga qué cambió en la normativa
eléctrica chilena desde el informe anterior: qué normas del corpus se modificaron o derogaron,
qué normas nuevas del sector publicó BCN, y en cada caso **qué cambió exactamente**.

## 2. Contexto

Lo que ya existe en el repo (leído el 2026-10-06):

| Pieza | Qué hace hoy | Brecha frente al objetivo |
|---|---|---|
| `scripts/monitor_run.sh` | Pasada completa: re-scrape → diff → informe → aplicar → reproceso → snapshot | Pensado semanal (lunes 06:00). **No hay crontab instalado** y el script hace `cd` a una ruta que ya no existe (`/home/alonso/Documentos/Github/energy-rag-postgres-rag`) |
| `scripts/rescrape_modificadas.py` | Re-baja las 70 normas en dominio, compara hash estable, throttle 20 s (~40 min) | Corre con `--frescura 6`: una norma no se vuelve a mirar hasta 6 días después |
| `scripts/monitor_diff.py` + `norma_evento` | Registra eventos por **norma** (`texto_modificado`, `version_nueva`, `estado_cambiado`, `vinculacion_nueva`, `articulo_derogado`, `norma_nueva`) con `impacto.citada_por` | No hay diff por **artículo** con antes→después |
| `scripts/monitor_report.py` | Escribe `docs/monitor-ultimo-informe.md` | Un solo archivo que se sobrescribe; sin historial por día; sin resumen en lenguaje claro |
| `scripts/aplicar_cambios.py` → `actualizar_norma.py` | Aplica al corpus con guardas (identidad, texto y articulado no encogen >10 %) | Ninguna; se reutiliza |
| `src/pipelines/update.py` | Diff contra un índice BCN inyectado | **El fetch es un TODO**: no hay descubrimiento de normas recién publicadas |
| `scripts/bajar_candidatas.py` + `ingerir_nuevas.py` | Descarga e ingesta validando identidad y dominio (corte 0.30) | Parte de una lista manual (`docs/descubrimiento-pendiente.md`), no de lo publicado en el día |
| `normas.organismo_normalizado` | Columna con `MIN_ENERGIA`, `CNE`, `SEC`, … | Existe para lo ingerido; no se usa para descubrir |

Restricciones del proyecto que aplican: sin API paga y LLM solo local (Ollama); BCN devuelve
429 por cuota; la RTX 3090 tiene una falla recurrente (Xid 79) y toda carga de GPU pasa por
el protocolo `gpu-seguridad`; la clasificación no puede tener regex como mecanismo principal
(orden dato → modelo → estructura → regla).

## 3. Decisiones fijadas

Las cinco que respondió el usuario. Nada fuera de esta lista está decidido.

| # | Tema | Decisión |
|---|---|---|
| D1 | Alcance | Cambios en las normas ya ingeridas **y** normas nuevas del sector eléctrico publicadas en BCN/LeyChile que el corpus no tiene |
| D2 | Entrega | **Solo archivo local**: un informe fechado por día, navegable como historial. Sin Discord, sin correo, sin notificación |
| D3 | Contenido | Por cada norma: lista exacta de artículos agregados / modificados / derogados con antes→después, **más** un párrafo en lenguaje claro escrito por `qwen3:30b-a3b` a partir de ese diff. Si la GPU falla, el informe sale igual solo con el diff |
| D4 | Corpus | Los cambios a normas ya ingeridas se aplican solos con las guardas actuales. Las normas nuevas **solo se informan** y quedan en una cola para aprobación manual |
| D5 | Filtro de nuevas | Entran las que modifican o derogan una norma del corpus y las publicadas por Ministerio de Energía, CNE o SEC. Cada una se puntúa con el filtro de dominio por embeddings (corte 0.30) y el informe muestra el puntaje |

## 4. Lo que sí y lo que no

**Sí entra**

- Detección diaria de cambios en las normas en dominio del corpus.
- Descubrimiento diario de normas nuevas en BCN según D5.
- Diff a nivel de artículo (agregado / modificado / derogado) con texto antes→después.
- Párrafo de resumen por norma generado por el LLM local a partir del diff.
- Un archivo de informe por día, conservado.
- Aplicación automática de cambios a normas existentes, con las guardas actuales.
- Cola de aprobación para normas nuevas.
- Dejar el proceso programado y operativo (ruta del script, crontab).

**No entra**

- Fuentes fuera de BCN: Diario Oficial, sitios de CNE, SEC o Coordinador.
- Notificaciones por cualquier canal.
- Ingesta automática de normas nuevas (ni embeddings de normas nuevas en la corrida diaria).
- Revisar todo lo que BCN publica en el día y filtrarlo por dominio.
- Cambios al pipeline de retrieval/generación del RAG o a sus métricas.
- Resolver la vigencia por norma (D1 del backlog, bloqueado por la cuota de BCN).

## 5. Criterios de aceptación (EARS)

**Programación e informe**

- CA-01 — El sistema deberá dejar escrito, cada día a más tardar a las 08:00, un archivo de
  informe identificado con la fecha de ese día.
- CA-02 — El sistema deberá conservar los informes de días anteriores sin sobrescribirlos.
- CA-03 — Cuando se genere un informe, el sistema deberá incluir solo los eventos detectados
  desde el informe anterior.
- CA-04 — El sistema deberá producir el informe sin enviar nada a servicios externos distintos
  de BCN.

**Cambios en normas del corpus (D1, D3)**

- CA-05 — Cuando el texto de una norma del corpus cambie en BCN, el sistema deberá listar en
  el informe cada artículo agregado, modificado o derogado.
- CA-06 — Cuando un artículo figure como modificado, el sistema deberá mostrar su texto
  anterior y su texto nuevo.
- CA-07 — Cuando una norma del corpus cambie, el sistema deberá indicar qué artículos del
  corpus la citan.
- CA-08 — Si la diferencia entre el texto guardado y el bajado es solo cosmética según el hash
  estable, entonces el sistema no deberá reportarla como cambio.
- CA-09 — Si el texto bajado está incompleto (placeholders `Loading...` o encogimiento más
  allá de la tolerancia), entonces el sistema deberá reportar la norma como "no verificada" y
  no como "sin cambios".

**Resumen LLM (D3)**

- CA-10 — Cuando una norma tenga un diff, el sistema deberá incluir un párrafo de resumen
  generado por `qwen3:30b-a3b` usando ese diff como única fuente.
- CA-11 — Si el LLM o la GPU no están disponibles, entonces el sistema deberá emitir el
  informe con el diff y marcar de forma visible que el resumen falta.
- CA-12 — Mientras se ejecute la generación del resumen, el sistema deberá operar bajo el
  protocolo de `gpu-seguridad`.

**Normas nuevas (D1, D5, D4)**

- CA-13 — Cuando BCN publique una norma que modifica o deroga una norma del corpus y que el
  corpus no tiene, el sistema deberá incluirla en el informe como norma nueva.
- CA-14 — Cuando BCN publique una norma del Ministerio de Energía, la CNE o la SEC que el
  corpus no tiene, el sistema deberá incluirla en el informe como norma nueva.
- CA-15 — Cuando se informe una norma nueva, el sistema deberá mostrar su puntaje de dominio
  y si supera el corte 0.30.
- CA-16 — Cuando se detecte una norma nueva, el sistema deberá agregarla a la cola de
  aprobación y no ingerirla.
- CA-17 — Si el título de lo descargado no coincide con el tipo y número de la norma
  esperada, entonces el sistema deberá descartarla del informe y registrarla como fallo de
  identidad.
- CA-18 — Si una norma nueva ya fue informada en un día anterior, entonces el sistema no
  deberá volver a informarla como nueva.

**Aplicación al corpus (D4)**

- CA-19 — Cuando se detecte un cambio en una norma del corpus y pase las guardas de
  `actualizar_norma`, el sistema deberá aplicarlo al corpus y decirlo en el informe.
- CA-20 — Si un cambio no pasa las guardas, entonces el sistema deberá dejar el corpus sin
  modificar para esa norma y listarla en el informe como pendiente de revisión manual.

**Robustez**

- CA-21 — Si BCN responde 429 durante la corrida, entonces el sistema deberá generar el
  informe con lo que alcanzó a revisar y listar las normas que quedaron sin revisar.
- CA-22 — Si Postgres no está levantado al iniciar, entonces el sistema deberá arrancar el
  contenedor `energy_rag_pg` antes de continuar.
- CA-23 — El sistema deberá registrar cada corrida en un log fechado dentro del proyecto.

## 6. Cómo se verifica

| Criterios | Verificación |
|---|---|
| CA-01, 02, 23 | Dejar el cron instalado tres días seguidos: existen tres informes y tres logs con fechas distintas, el más reciente con hora de modificación ≤ 08:00 |
| CA-03, 18 | Dos corridas consecutivas sin cambios en BCN: la segunda no repite eventos ni normas nuevas de la primera |
| CA-04 | Revisión del código: ninguna llamada de red fuera de `bcn.cl` y `localhost` (Ollama, Postgres) |
| CA-05, 06, 07 | Test con fixture: dos versiones de una misma norma con un artículo agregado, uno modificado y uno derogado conocidos; el informe los lista con antes→después y con `citada_por` |
| CA-08 | Test con el caso ya medido (LEY 20365, similitud 1.0000): cero eventos |
| CA-09 | Test con un JSON que contiene `Loading...`: aparece como "no verificada" |
| CA-10 | Revisión manual de una muestra de resúmenes contra su diff: cada afirmación del párrafo está en el diff (tamaño de la muestra: ver PA-10) |
| CA-11, 12 | Corrida con Ollama detenido: el informe se escribe, trae el diff y la marca de resumen faltante; el log muestra el paso por `gpu_guard.sh` |
| CA-13, 14, 15, 16 | Corrida sobre una fecha pasada con publicaciones conocidas (ej. una norma de `docs/descubrimiento-pendiente.md` Fuente 2 con fecha conocida): aparece con puntaje, queda en la cola, y `normas` no cambia de conteo |
| CA-17 | Test con el caso ya medido (`DECRETO 42` → `ACUERDO 42`): no entra al informe |
| CA-19, 20 | Test con una norma que pasa las guardas y otra cuyo texto encoge >10 %: la primera se actualiza, la segunda queda intacta y listada |
| CA-21 | Test con el crawler simulando 429 a mitad de corrida: informe parcial con la lista de no revisadas |
| CA-22 | Corrida con el contenedor detenido |
| General | `pytest tests/` sin regresiones; el eval de no-regresión del RAG tras la primera aplicación automática al corpus |

## 7. Preguntas abiertas

Ninguna de estas está decidida. Las marcadas ⚠️ bloquean el diseño.

- **PA-01 ⚠️ Fuente de "lo publicado hoy" en BCN.** No está verificado que BCN ofrezca un
  listado de publicaciones recientes filtrable por organismo o por fecha. Sin eso, la parte
  "publicadas por Ministerio de Energía / CNE / SEC" de D5 no tiene de dónde salir. Hay que
  investigarlo antes de diseñar el descubrimiento.
- **PA-02 ⚠️ Cuota 429 con corrida diaria.** Hoy se revisan 70 normas una vez por semana
  (`--frescura 6`). Revisarlas a diario multiplica las peticiones por siete y la misma cuota
  ya bloquea otro trabajo del backlog. ¿Se revisan las 70 cada día, o se rota un subconjunto?
  Si se rota, un cambio puede aparecer en el informe con días de atraso.
- **PA-03 Hora de inicio.** El scrape actual tarda ~40 min. ¿A qué hora parte el cron para
  llegar a las 08:00, y qué pasa si a las 08:00 no terminó (informe parcial o informe tardío)?
- **PA-04 Días sin cambios.** ¿Se escribe igual un archivo que diga "sin cambios", o no se
  escribe nada? (Sin archivo no se distingue "no pasó nada" de "no corrió".)
- **PA-05 Máquina apagada o corrida fallida.** ¿La corrida siguiente cubre los días perdidos
  en un solo informe, genera un informe por cada día faltante, o los días perdidos se pierden?
- **PA-06 Monitor semanal.** ¿El proceso diario reemplaza a `monitor_run.sh` o conviven?
- **PA-07 Ubicación y nombre de los informes.** Directorio y formato de nombre (¿`docs/…`,
  `data/…`?), y si los informes diarios se commitean o se ignoran en git.
- **PA-08 Cola de aprobación.** ¿Dónde vive (tabla, archivo, sección de
  `docs/descubrimiento-pendiente.md`) y con qué comando se aprueba o rechaza una norma?
- **PA-09 Nuevas bajo el corte 0.30.** D5 pide mostrar el puntaje, pero no dice si una norma
  de CNE/SEC/Energía que puntúa bajo el corte aparece igual en el informe o se omite.
- **PA-10 Fidelidad del resumen LLM.** ¿Qué control se exige para que el párrafo no afirme
  nada que no esté en el diff (solo revisión manual de una muestra, o un chequeo automático),
  y de qué tamaño es la muestra de aceptación?
- **PA-11 Diffs muy grandes.** Una norma reemplazada casi entera puede no caber en el
  contexto del LLM. ¿Se resume por partes, se trunca, o se omite el resumen?
- **PA-12 GPU y Xid 79.** La generación diaria es carga de GPU desatendida. ¿Con qué tope de
  potencia corre, y está permitido re-habilitar un cron con GPU dado el historial de fallas?
- **PA-13 Cambios que no pasan las guardas.** Quedan pendientes (CA-20), pero ¿se repiten en
  el informe de cada día hasta resolverse, o solo el día en que se detectan?
- **PA-14 Normas `fuera_de_dominio`.** El corpus tiene normas marcadas fuera de dominio que
  el monitor actual no vigila. ¿Siguen fuera del informe diario?
- **PA-15 Idioma y forma del informe.** Markdown como el actual es la suposición natural,
  pero no está pedido. ¿Algún orden o sección obligatoria (ej. lo crítico primero)?
- **PA-16 Baseline del eval.** La aplicación automática diaria cambia el corpus sin revisión.
  ¿Hay que correr el eval de no-regresión después de cada aplicación, o solo a demanda?
