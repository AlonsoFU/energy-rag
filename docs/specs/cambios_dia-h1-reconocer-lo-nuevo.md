# Spec — Historia 1: reconocer lo nuevo en BCN Chile

Estado: **borrador para revisión** · 2026-10-13 · sin código escrito todavía.
Spec madre: [`cambios_dia.md`](cambios_dia.md) (D1, D4, D5 · CA-13 a CA-18 · PA-01).

> El spec madre no está partido en historias. Esta historia se **derivó** de su bloque
> "Normas nuevas"; el recorte (§3) es una propuesta y hay que confirmarlo.

## 1. Historia

**Como** responsable del corpus de normativa eléctrica,
**quiero** que el sistema reconozca en cada corrida las normas que BCN/LeyChile publicó y que
el corpus no tiene,
**para** enterarme de lo nuevo del sector sin revisar BCN a mano y decidir yo qué se ingiere.

"Reconocer" termina cuando la norma queda **registrada como candidata**, con su identidad
verificada, el motivo por el que entró y su puntaje de dominio. Mostrarla en el informe,
resumirla o ingerirla son otras historias.

## 2. Contexto

Lo que ya existe y lo que falta (leído el 2026-10-13):

| Pieza | Qué hace hoy | Brecha para esta historia |
|---|---|---|
| `src/pipelines/update.py` | `diff_against_db` compara un índice BCN inyectado contra `descargas_estado` | **El fetch es un TODO**: nadie produce ese índice |
| `scripts/extract_vinculaciones.py` | Lee `nav_vinc_modificacion?idNorma=` de una norma del corpus y saca quién la modifica | No corre a diario ni cruza contra el corpus para decir "esta falta" |
| `docs/descubrimiento-pendiente.md` Fuente 2 | Lista de 10+ `id_norma` que modifican a las nuestras y faltan | Lista manual, generada una vez |
| `scripts/bajar_candidatas.py` | Baja una candidata, valida identidad, calcula `dominio_sim` (corte 0.30) | Parte de la lista manual; resuelve tipo+número con el buscador (9 de 24 descargas eran otra norma) |
| `norma_evento.tipo_evento = 'norma_nueva'` | Hoy significa "apareció una norma **en el corpus**" (post-ingesta) | No hay forma de registrar "publicada en BCN y **no** ingerida" |
| `normas.organismo_normalizado` | `MIN_ENERGIA`, `CNE`, `SEC`, … para lo ya ingerido | No se usa para descubrir |

**Verificado el 2026-10-13 sobre PA-01** (una sola petición, sin 429):
`https://www.leychile.cl/Consulta/obtxml?opt=3&cantidad=N` devuelve las últimas N normas
publicadas con `idNorma`, `TIPO`, `NUMERO`, `TITULO`, `ORGANISMO`, `FECHA_PUBLICACION` y
`FECHA_PROMULGACION`. **Las cinco devueltas eran leyes** (`DESCRIPCION = Ley`); no está
verificado que el endpoint entregue decretos ni resoluciones, que es donde publican el
Ministerio de Energía, la CNE y la SEC. La portada de últimas publicaciones
(`consulta/portada_ulp`) se arma por JavaScript y no se pudo leer sin navegador.
→ PA-01 queda **resuelta a medias**: hay fuente para leyes, falta para decretos y
resoluciones (H1-PA-01).

## 3. Alcance

**Sí entra**

- Las dos vías de reconocimiento de D5:
  - **Vía V (vinculación):** normas que modifican o derogan una norma del corpus.
  - **Vía O (organismo):** normas publicadas por Ministerio de Energía, CNE o SEC.
- Decidir si una norma es nueva respecto del corpus y de lo ya reconocido antes.
- Verificar la identidad de lo descargado.
- Puntaje de dominio por embeddings sobre el articulado, con el corte 0.30.
- Registrar la candidata y dejarla en la cola de aprobación.
- Dejar constancia de lo que **no** se alcanzó a revisar.

**No entra**

- Redactar o dar formato al informe diario (CA-01 a CA-04 del spec madre).
- Cambios en normas ya ingeridas, diff por artículo y resumen LLM (CA-05 a CA-12).
- Aprobar, rechazar o ingerir candidatas (CA-19, CA-20; comando de la cola: PA-08).
- Fuentes fuera de BCN (Diario Oficial, sitios de CNE, SEC, Coordinador).
- Revisar todo lo que BCN publica y filtrarlo por dominio.
- Programación del cron.

## 4. Definiciones

- **Corpus:** las filas de `normas`, incluidas las marcadas `fuera_de_dominio`.
- **Norma nueva:** norma con `idNorma` de BCN que no está en el corpus.
- **Candidata:** norma nueva reconocida por la vía V, la vía O o ambas.
- **Reconocida antes:** candidata registrada en una corrida previa, en cualquier estado
  (pendiente, aprobada, rechazada).
- **Ventana:** período que cubre una corrida. Supuesto S1 (§8).

## 5. Criterios de aceptación (EARS)

Patrones: ubicuo ("El sistema deberá…"), evento ("Cuando…"), estado ("Mientras…"),
comportamiento no deseado ("Si…, entonces…"). Entre paréntesis, el criterio del spec madre
que refina.

**Qué cuenta como nuevo**

- H1-CA-01 — El sistema deberá tratar como norma nueva únicamente a las normas cuyo `idNorma`
  no esté en el corpus.
- H1-CA-02 — Si una norma está en el corpus marcada `fuera_de_dominio`, entonces el sistema
  no deberá reconocerla como nueva.
- H1-CA-03 — Si una norma fue reconocida antes, entonces el sistema no deberá volver a
  registrarla como candidata. (CA-18)
- H1-CA-04 — El sistema deberá identificar cada candidata por su `idNorma` de BCN y no por
  tipo y número.

**Vía V — modifica o deroga una norma del corpus**

- H1-CA-05 — Cuando BCN muestre, para una norma en dominio del corpus, una vinculación de
  modificación o derogación cuya norma de origen no está en el corpus, el sistema deberá
  registrar esa norma de origen como candidata. (CA-13)
- H1-CA-06 — Cuando se registre una candidata por la vía V, el sistema deberá guardar qué
  norma del corpus afecta y con qué relación (modifica o deroga).
- H1-CA-07 — Cuando una candidata afecte a más de una norma del corpus, el sistema deberá
  guardar todas las normas afectadas en una sola candidata.
- H1-CA-29 — Cuando se ejecute una corrida, el sistema deberá consultar las vinculaciones de
  todas las normas en dominio del corpus, sin rotar ni muestrear. (H1-D1)
- H1-CA-30 — El sistema deberá leer las vinculaciones desde la página de vinculaciones de BCN
  de cada norma y no inferirlas solo del texto ya descargado. (H1-D1)
- H1-CA-31 — Si en la corrida anterior quedaron normas del corpus sin revisar, entonces el
  sistema deberá revisarlas primero en la corrida siguiente. (H1-D1)

**Vía O — publicada por Ministerio de Energía, CNE o SEC**

- H1-CA-08 — Cuando el listado de publicaciones de BCN incluya, dentro de la ventana, una
  norma nueva cuyo organismo sea el Ministerio de Energía, la CNE o la SEC, el sistema deberá
  registrarla como candidata. (CA-14)
- H1-CA-09 — El sistema deberá decidir el organismo a partir del campo de organismo que
  entrega BCN, normalizado a los mismos valores de `normas.organismo_normalizado`, y no a
  partir del título ni del texto de la norma.
- H1-CA-10 — Si el organismo de una norma del listado viene vacío o no se puede normalizar,
  entonces el sistema deberá contarla en el registro de la corrida como "organismo no
  reconocido" y no descartarla en silencio.

**Registro de la candidata**

- H1-CA-11 — Cuando se reconozca una candidata, el sistema deberá guardar: `idNorma`, tipo,
  número, título, organismo, fecha de publicación, URL en BCN, vía o vías por las que entró
  y fecha de detección.
- H1-CA-12 — Cuando una misma norma sea reconocida por la vía V y por la vía O, el sistema
  deberá registrar una sola candidata con ambos motivos.
- H1-CA-13 — Cuando se registre una candidata, el sistema deberá agregarla a la cola de
  aprobación en estado pendiente. (CA-16)
- H1-CA-14 — El sistema no deberá insertar ni modificar filas de `normas` ni de `articulos`
  al reconocer candidatas. (CA-16, D4)

**Identidad y texto**

- H1-CA-15 — Si el tipo y número que declara el texto descargado no coinciden con los de la
  candidata, entonces el sistema deberá excluirla de la cola y registrarla como fallo de
  identidad. (CA-17)
- H1-CA-16 — Si el texto descargado está incompleto (placeholders `Loading...`), entonces el
  sistema deberá registrar la candidata con puntaje "no disponible" y reintentar la descarga
  en la corrida siguiente.

**Puntaje de dominio**

- H1-CA-17 — Cuando se reconozca una candidata con texto completo, el sistema deberá
  calcular su puntaje de dominio sobre el articulado, con el mismo método y la misma
  referencia que usa `marcar_fuera_dominio`. (CA-15)
- H1-CA-18 — Cuando se calcule el puntaje, el sistema deberá guardar el valor y si alcanza el
  corte 0.30. (CA-15)
- H1-CA-19 — El sistema no deberá usar el puntaje de dominio para decidir si una norma entra
  como candidata; la entrada la deciden solo las vías V y O. (D5)
- H1-CA-20 — Si el embedder o la GPU no están disponibles, entonces el sistema deberá
  registrar la candidata con puntaje "no disponible" y calcularlo en la corrida siguiente.
- H1-CA-21 — Mientras se calcule el puntaje de dominio, el sistema deberá operar bajo el
  protocolo de `gpu-seguridad`. (CA-12)

**Cobertura y fallos**

- H1-CA-22 — Cuando termine una corrida, el sistema deberá dejar registrado, por cada vía:
  cuántas normas revisó, cuántas candidatas registró y cuáles quedaron sin revisar.
- H1-CA-23 — Si BCN responde 429 o una fuente no responde, entonces el sistema deberá
  conservar las candidatas ya registradas y listar lo que quedó sin revisar. (CA-21)
- H1-CA-24 — Si una vía no pudo consultarse completa, entonces el sistema no deberá declarar
  "sin normas nuevas" para esa vía.
- H1-CA-25 — Cuando la corrida anterior no haya terminado bien, el sistema deberá extender la
  ventana hasta la última corrida que sí terminó. (S1)
- H1-CA-26 — Si la ventana excede lo que el listado de BCN alcanza a mostrar, entonces el
  sistema deberá registrar que hubo un tramo sin cubrir.
- H1-CA-27 — El sistema deberá respetar entre peticiones a BCN el mismo intervalo mínimo que
  usa el monitor (20 s por defecto).
- H1-CA-28 — El sistema no deberá hacer peticiones de red a destinos distintos de BCN/LeyChile
  y `localhost`. (CA-04)

## 6. Cómo se verifica

| Criterios | Verificación |
|---|---|
| H1-CA-01, 02, 04 | Test con fixture de listado que mezcla una norma del corpus, una `fuera_de_dominio` y una ausente: solo la ausente queda como candidata |
| H1-CA-03, 12 | Dos corridas seguidas sobre los mismos fixtures: la segunda registra 0 candidatas; una norma presente en ambas vías ocupa una sola fila con dos motivos |
| H1-CA-05, 06, 07 | Test con fixture de `nav_vinc_modificacion` de dos normas del corpus modificadas por la misma norma ausente: una candidata con dos normas afectadas y su relación |
| H1-CA-29, 30, 31 | Corrida completa: el registro muestra tantas normas revisadas en la vía V como normas en dominio tiene el corpus, cada una con su petición a `nav_vinc_modificacion`. Tras una corrida cortada por 429, la siguiente empieza por las pendientes |
| H1-CA-08, 09, 10 | Test con fixture de `obtxml?opt=3` con organismos Energía, CNE, SEC, otro ministerio y uno vacío: entran tres, el ministerio ajeno no, el vacío se cuenta como no reconocido |
| H1-CA-11, 13, 14 | Tras una corrida con candidatas: la cola tiene todos los campos y `count(*)` de `normas` y `articulos` no cambió |
| H1-CA-15 | Test con el caso ya medido (`DECRETO 42` → `ACUERDO 42`): queda como fallo de identidad, fuera de la cola |
| H1-CA-16, 20 | Test con texto `Loading...` y corrida con Ollama detenido: candidata registrada con puntaje "no disponible"; la corrida siguiente lo completa |
| H1-CA-17, 18, 19 | Casos ya medidos: DS 44 (0.579) y DS 88 (0.591) quedan sobre el corte; LEY 21150 (0.191) queda bajo el corte **y sigue registrada**. Tolerancia ±0.01 frente a `marcar_fuera_dominio` |
| H1-CA-21 | El log muestra el paso por `gpu_guard.sh` antes del primer embedding |
| H1-CA-22, 23, 24 | Test con el crawler simulando 429 a mitad de la vía V: las candidatas previas persisten, el registro lista las normas no revisadas y no dice "sin normas nuevas" |
| H1-CA-25, 26 | Test con última corrida exitosa hace 5 días y listado que solo cubre 2: registra las de esos 2 días y el tramo sin cubrir |
| H1-CA-27, 28 | Revisión del código y del log: intervalo entre peticiones ≥ 20 s; ningún host fuera de `bcn.cl`, `leychile.cl` y `localhost` |
| Aceptación en vivo | Una corrida real sobre una ventana pasada con publicación conocida del sector: la norma aparece como candidata con su vía y su puntaje |
| General | `pytest tests/` sin regresiones |

## 7. Decisiones fijadas

- **H1-D1 (2026-10-13, usuario) — En la vía V manda la precisión sobre la cuota.** Se revisan
  las vinculaciones de todas las normas en dominio en cada corrida. No se rota (una norma
  nueva aparecería con días de atraso) ni se depende de lo que traiga la descarga del
  monitor. Costo aceptado: una petición por norma en dominio y por corrida (~70, ~25 min a
  20 s) y más exposición al 429; lo cubren H1-CA-23, 24 y 31. A escala este costo crece con
  el corpus y habrá que revisarlo.

## 8. Supuestos

Tomados para poder escribir los criterios. Si alguno es falso, cambian los criterios que
lo citan.

- **S1 — La ventana es "desde la última corrida exitosa", no "el día de hoy".** Con "hoy",
  un día con la máquina apagada pierde normas para siempre. Afecta H1-CA-08, 25, 26. El spec
  madre deja abierto qué pasa con el **informe** de los días perdidos (PA-05); aquí solo se
  fija que el reconocimiento no las pierda.
- **S2 — La vía V solo mira normas en dominio del corpus**, igual que el monitor actual
  (PA-14 del spec madre sigue abierta).
- **S3 — El `idNorma` es la llave de identidad.** El listado y las vinculaciones ya lo traen,
  así que no hace falta resolver tipo+número con el buscador, que es donde nacían los
  fallos de identidad.

## 9. Preguntas abiertas

Las marcadas ⚠️ bloquean el diseño de esta historia.

- **H1-PA-01 ⚠️ Fuente de decretos y resoluciones para la vía O.** `obtxml?opt=3` está
  verificado solo para leyes. Falta comprobar si entrega otros tipos, o si hay que leer la
  portada de últimas publicaciones con navegador (el repo ya usa Playwright). Sin esto la
  vía O cubre solo leyes, que es la parte menor de lo que publican Energía, CNE y SEC.
- **H1-PA-02 — cerrada por H1-D1.** Queda un derivado no bloqueante: si la corrida diaria
  del monitor y la vía V suman demasiadas peticiones, en qué orden corren (PA-02 del spec
  madre).
- **H1-PA-03 Dónde vive la candidata.** `norma_evento.norma_nueva` hoy significa "entró al
  corpus". ¿Tipo de evento nuevo, tabla propia para la cola, o ambas? Depende de PA-08.
- **H1-PA-04 Candidatas bajo el corte.** H1-CA-19 las registra siempre; si después se
  muestran o se omiten es PA-09 del spec madre.
- **H1-PA-05 Resoluciones que BCN no indexa.** `docs/descubrimiento-pendiente.md` Fuente 3
  dice que CNE, SEC y CEN publican resoluciones fuera de BCN. Queda fuera por D1, pero esta
  historia no las verá: conviene decirlo en el informe.
- **H1-PA-06 Rechazadas que vuelven.** Si una candidata rechazada recibe después una
  vinculación nueva hacia el corpus, ¿se reabre o sigue rechazada? H1-CA-03 hoy la deja
  rechazada.
- **H1-PA-07 Profundidad del listado.** Cuántas publicaciones hacia atrás se piden por
  corrida (`cantidad=N`) para que S1 se cumpla sin gastar cuota de más.
- **H1-PA-08 Falsos positivos del corte.** `DECRETO 30` (transporte) puntuó 0.341. El
  puntaje es informativo en esta historia, pero quien apruebe debe saber que el corte no
  separa bien en la zona 0.30–0.35.
