# Tareas — Historia 1: reconocer lo nuevo en BCN Chile

Estado: **propuesta** · 2026-10-13 · desglose de
[`cambios_dia-h1-reconocer-lo-nuevo.md`](cambios_dia-h1-reconocer-lo-nuevo.md).

Cada tarea cabe en una sesión corta, deja tests y no toca el pipeline del RAG. Los nombres
de archivos, tablas y funciones son **propuestas**: el spec no los fija.

Reglas que aplican a todas:

- Test primero, con fixtures guardados; ningún test hace peticiones a BCN.
- Nada inserta ni modifica `normas` ni `articulos` (H1-CA-14).
- Antes de escribir cualquier lista o regex que clasifique, invocar la skill
  `sin-hardcodeo-en-experimentos`.
- Carga de GPU solo bajo `gpu-seguridad`.

## Estado (2026-10-13)

Primera tanda implementada y revisada. Cada rama parte de `7643a68` y **no está integrada**.

| Tarea | Rama | Commit | Tests | Revisión |
|---|---|---|---|---|
| T00 fuente de decretos | (en el spec, §9) | — | — | Hecha: `obtxml?opt=3` solo entrega leyes; las vinculaciones requieren navegador |
| T01 esquema | `worktree-agent-aa77f60d84116e9e0` | `5b53c6d` | 7 escritos, **0 ejecutados** (sin Postgres) | Aprobada por lectura, condicionada a ejecutar |
| T03 cliente BCN | `worktree-agent-a753cd86753c9d9da` | `12c0984` | 42 pasan | Aprobada en la tercera vuelta |
| T04 listado | `worktree-agent-ab00292f3f102a3ba` | `cb6de4f` | 7 pasan | Aprobada |
| T14 scorer de dominio | `worktree-agent-af2aecb7bd769a5ac` | `95f9de8` | 20 pasan | Aprobada en la segunda vuelta |

Lo que las revisiones dejaron para las tareas siguientes:

- **T05:** un listado que parsea pero viene vacío o con otra raíz no es "sin normas nuevas";
  se trata como vía incompleta (H1-CA-24). Una `Publicacion` puede traer `tipo` y `numero`
  vacíos: decidir si se descarta.
- **T09:** `estado`, `vias`, `afecta`, `organismos` y `detalle` son `NOT NULL`; se insertan
  listas u objetos vacíos, nunca null.
- **T03 (menor):** `construir_opener(*manejadores_extra)` acepta handlers extra para los
  tests; un handler de redirección pasado ahí las reactivaría. Hoy nadie lo llama con
  argumentos. Conviene dejar la inyección solo del lado del test.
- **T13:** los `id_norma` se comparan como texto literal en el scorer (`1.0` o `" 1"` no
  calzan con `1`); el conjunto etiquetado debe guardar el id tal cual lo entrega BCN.

Bloqueos para seguir:

- **Entorno:** esta máquina no tiene el `venv` del proyecto, Docker está inactivo y no hay
  Ollama ni Playwright. Sin Postgres no se verifican T01, T02, T05, T09, T10, T16; sin
  navegador no se hacen T06, T07, T08; sin GPU no se hacen T11, T15, T17.
- **Integración:** T05 necesita T01 y T04 juntas; T07 necesita T02 y T06. Hay que integrar
  las ramas aprobadas en una rama común antes de la segunda tanda.
- **Decisiones del usuario:** H1-PA-01 (fuente de decretos y resoluciones, sin resolver),
  H1-PA-09 (umbral 0.90 y tamaño del conjunto) y la validación de etiquetas de T13.

## Orden y dependencias

- **Carril A (registro):** T01 → T02 → T09 → T16
- **Carril B (fuentes):** T03 → T04 → T05 · T03 → T06 → T07 · T03 → T08 → T10
- **Carril C (precisión de dominio):** T13 → T14 → T15 · T10 → T11 → T12
- **Cierre:** T16 → T17 → T18
- **T00** corre en paralelo; solo condiciona a T05 para decretos y resoluciones.

Los tres carriles (fuentes, registro, precisión de dominio) se pueden trabajar en paralelo.

## Investigación

### T00 — Fuente de decretos y resoluciones recién publicados
- **Cubre:** H1-PA-01, H1-PA-07.
- **Hacer:** probar si `obtxml?opt=3` entrega tipos distintos de ley; si no, leer la portada
  de últimas publicaciones con Playwright. Guardar una respuesta real como fixture.
- **Terminado cuando:** el spec dice de dónde sale cada tipo de norma y cuántas
  publicaciones hacia atrás alcanza la fuente, o dice que no hay fuente.
- **Bloqueo:** requiere permiso para unas pocas peticiones a BCN.

## Carril A — Registro

### T01 — Esquema de candidatas y de corridas
- **Cubre:** H1-CA-11, 13, 40 · resuelve H1-PA-03.
- **Hacer:** DDL idempotente (al estilo de `scripts/monitor_schema.py`) para una tabla de
  candidatas (llave `id_norma`, estado, vías, normas afectadas, puntaje, clase, embedder y
  versión de la referencia) y una de corridas (ventana, conteos por vía, no revisadas).
- **Terminado cuando:** correr el DDL dos veces no falla y un test inserta y lee una
  candidata con todos los campos de H1-CA-11.

### T02 — Decidir si una norma es nueva
- **Cubre:** H1-CA-01, 02, 03, 04.
- **Hacer:** función que recibe `id_norma` y responde nueva / en corpus / reconocida antes.
- **Terminado cuando:** pasa el test con una norma del corpus, una `fuera_de_dominio`, una
  ya reconocida en cada estado y una ausente.
- **Depende de:** T01.

### T09 — Fusionar vías y encolar
- **Cubre:** H1-CA-07, 12, 13, 14.
- **Hacer:** unir los hallazgos de las vías V y O por `id_norma`, acumular motivos y normas
  afectadas, insertar como pendiente.
- **Terminado cuando:** una norma presente en ambas vías ocupa una fila con dos motivos, una
  segunda corrida idéntica inserta 0 filas y los conteos de `normas` y `articulos` no cambian.
- **Depende de:** T02.

### T16 — Registro de cobertura de la corrida
- **Cubre:** H1-CA-22, 24, 42.
- **Hacer:** al cerrar la corrida, guardar por vía: revisadas, candidatas, no revisadas, y
  el conteo por clase de dominio. Una vía incompleta nunca queda como "sin normas nuevas".
- **Terminado cuando:** el test con una vía cortada produce un registro que lista las no
  revisadas y marca la vía como incompleta.
- **Depende de:** T09, T12.

## Carril B — Fuentes de BCN

### T03 — Cliente BCN con intervalo, 429 y lista de hosts
- **Cubre:** H1-CA-23, 27, 28.
- **Hacer:** un único punto de salida a red: intervalo mínimo de 20 s, corte ordenado ante
  429, rechazo de cualquier host fuera de `bcn.cl`, `leychile.cl` y `localhost`.
- **Terminado cuando:** tests con reloj y transporte simulados prueban el intervalo, el corte
  por 429 sin perder lo ya obtenido y el rechazo de un host ajeno.

### T04 — Leer el listado de publicaciones
- **Cubre:** H1-CA-08 (parte), 11.
- **Hacer:** parser del XML de `obtxml?opt=3` a registros con `id_norma`, tipo, número,
  título, organismo, fecha de publicación y URL.
- **Terminado cuando:** el fixture real de 5 leyes del 2026-10-13 se convierte en 5
  registros completos.
- **Depende de:** T03.

### T05 — Vía O: ventana y filtro por organismo
- **Cubre:** H1-CA-08, 09, 10, 25, 26.
- **Hacer:** normalizar el organismo a los valores de `normas.organismo_normalizado` usando
  como dato los pares organismo→normalizado que ya hay en el corpus; filtrar Energía, CNE y
  SEC dentro de la ventana "desde la última corrida exitosa"; registrar el tramo sin cubrir.
- **Terminado cuando:** pasa el test con cinco organismos (tres que entran, un ministerio
  ajeno, uno vacío contado como no reconocido) y el de ventana de 5 días con listado de 2.
- **Depende de:** T04, T01.

### T06 — Leer las vinculaciones de una norma
- **Cubre:** H1-CA-05 (parte), 06, 30.
- **Hacer:** parser de la página `nav_vinc_modificacion` a pares (norma de origen, relación),
  reutilizando lo que sirva de `scripts/extract_vinculaciones.py`.
- **Terminado cuando:** un fixture real de una norma del corpus devuelve sus modificatorias
  con `id_norma` y relación.
- **Depende de:** T03.

### T07 — Vía V: recorrer las normas en dominio
- **Cubre:** H1-CA-05, 29, 31, 32.
- **Hacer:** recorrer todas las normas en dominio (nunca las `fuera_de_dominio`), empezando
  por las que quedaron sin revisar; quedarse con los orígenes que son normas nuevas.
- **Terminado cuando:** el test visita exactamente las normas en dominio, y tras una corrida
  cortada la siguiente empieza por las pendientes.
- **Depende de:** T06, T02.

### T08 — Bajar el texto de una candidata por `id_norma`
- **Cubre:** H1-CA-16 (parte).
- **Hacer:** descarga directa por `id_norma` (sin el buscador por tipo y número) reutilizando
  `src/crawlers/norm_detail_crawler.py`; detectar texto incompleto (`Loading...`).
- **Terminado cuando:** un fixture completo devuelve texto y uno con `Loading...` devuelve
  "incompleto".
- **Depende de:** T03.

### T10 — Verificar identidad
- **Cubre:** H1-CA-15, 16.
- **Hacer:** comparar tipo y número declarados en el texto bajado con los de la candidata;
  el fallo queda registrado y fuera de la cola; el texto incompleto deja la candidata con
  puntaje "no disponible" para reintento.
- **Terminado cuando:** el caso `DECRETO 42` → `ACUERDO 42` queda como fallo de identidad.
- **Depende de:** T08, T09.

## Carril C — Precisión de dominio

### T11 — Puntaje de dominio de una candidata
- **Cubre:** H1-CA-17, 18, 19, 20, 21, 40.
- **Hacer:** calcular el puntaje sobre el articulado con el método de
  `scripts/marcar_fuera_dominio.py`; guardar valor, si alcanza 0.30, embedder y versión de
  la referencia; pasar por `gpu_guard.sh`; sin embedder, dejar "no disponible".
- **Terminado cuando:** DS 44, DS 88 y LEY 21150 reproducen sus puntajes medidos (±0.01) y
  con Ollama detenido la candidata queda registrada sin puntaje.
- **Depende de:** T10.

### T12 — Clasificar en tres clases
- **Cubre:** H1-CA-34, 35, 36, 41.
- **Hacer:** asignar "en dominio", "dudosa" o "fuera de dominio" leyendo los límites de un
  archivo de calibración; conservar las de la vía V como "relevante por vinculación";
  recalcular las pendientes si cambia el embedder o la referencia.
- **Terminado cuando:** pasan los tests de las tres clases, el de la vía V bajo el corte y
  el de cambio de versión.
- **Depende de:** T11, T15 (para la calibración real; antes usa una de prueba).

### T13 — Conjunto etiquetado de dominio
- **Cubre:** H1-CA-39 · resuelve parte de H1-PA-09.
- **Hacer:** armar el conjunto leyendo cada norma (no su puntaje), con etiqueta y motivo;
  incluir DS 44, DS 88, LEY 21719, LEY 21150, LEY 20955, DECRETO 30 y DFL 1 Tránsito;
  partir en dev y held-out antes de mirar puntajes.
- **Terminado cuando:** el archivo existe en `data/eval/`, el usuario validó las etiquetas y
  la partición quedó congelada.
- **Sin dependencias.** Requiere revisión del usuario.

### T14 — Scorer de precisión de dominio
- **Cubre:** H1-CA-37, 38.
- **Hacer:** script que puntúa el conjunto etiquetado y entrega precisión de "en dominio",
  normas en dominio que cayeron fuera, y conteo de dudosas y sin puntaje, por partición.
  Declarar en la cabecera cómo puntúa "dudosa" y "sin puntaje" antes de correrlo. Guardar
  el puntaje de cada norma, no solo el resultado.
- **Terminado cuando:** un test con puntajes inventados da los números esperados a mano.
- **Depende de:** T13.

### T15 — Calibrar la zona dudosa y medir
- **Cubre:** H1-CA-35, 37, 38.
- **Hacer:** fijar los límites de "dudosa" con dev, guardarlos como dato, y medir una sola
  vez sobre held-out. Si no se alcanza 0.90 o cae fuera una norma en dominio, anotar el
  resultado y volver al usuario: no ajustar contra held-out.
- **Terminado cuando:** el resultado de dev y de held-out está guardado en
  `data/eval/results/` y anotado en el backlog con su número.
- **Depende de:** T11, T14.

## Cierre

### T17 — Orquestador y corrida en vivo
- **Cubre:** aceptación en vivo · H1-CA-25.
- **Hacer:** un comando que ejecuta vía V, vía O, fusión, identidad, puntaje, clasificación
  y registro; modo `--dry` que no escribe.
- **Terminado cuando:** una corrida real sobre una ventana con una publicación conocida del
  sector deja esa norma como candidata con vía, puntaje y clase.
- **Depende de:** T16. Gasta cuota de BCN (~70 peticiones): correr una vez.

### T18 — Documentación y backlog
- **Cubre:** regla "marcar el backlog" de `CLAUDE.md`.
- **Hacer:** actualizar `docs/sistema/03-actualizacion-bcn.md` (sección "Normas nuevas"),
  marcar la entrada en `docs/bitacora/backlog-mejoras.md` con el resultado de T15 y cerrar
  en el spec las preguntas que quedaron resueltas.
- **Terminado cuando:** el spec no tiene preguntas ⚠️ abiertas o dice por qué siguen.
- **Depende de:** T17.

## Trazabilidad

| Criterios | Tarea |
|---|---|
| H1-CA-01 a 04 | T02 |
| H1-CA-05, 06, 30 | T06, T07 |
| H1-CA-07, 12, 13, 14 | T09 |
| H1-CA-08, 09, 10, 25, 26 | T04, T05 |
| H1-CA-11 | T01, T04 |
| H1-CA-15, 16 | T08, T10 |
| H1-CA-17 a 21, 40 | T11 |
| H1-CA-22, 24, 42 | T16 |
| H1-CA-23, 27, 28 | T03 |
| H1-CA-29, 31, 32 | T07 |
| H1-CA-33 | revisión en T11 y T12 |
| H1-CA-34, 35, 36, 41 | T12, T15 |
| H1-CA-37, 38 | T14, T15 |
| H1-CA-39 | T13 |
