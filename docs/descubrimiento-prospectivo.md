# Descubrimiento prospectivo — cómo enterarse de normativa NUEVA

Estado: **NO RESUELTO**. Documentado para no repetir la exploración.

## El hueco

El descubrimiento que existe (`scripts/descubrir_normativa.py`) es **retrospectivo**: encuentra
normas que el corpus YA cita y no tiene. Sirvió para traer la Ley 20.936. Pero:

```
ley nueva que modifica una norma del corpus  ->  se detecta, con retraso (via vinculaciones)
ley nueva independiente                       ->  NO se detecta
resolucion CNE/SEC/CEN nueva                  ->  NO se detecta
```

Una norma publicada ayer no la cita nadie todavía. Puede pasar un año hasta que aparezca.

## Qué se probó (2026-08-23)

| Fuente | Resultado |
|---|---|
| BCN `listaresultadosimple?cadena=` | **solo busca por NÚMERO**. Con texto ("peajes de transmision", "precios de nudo") devuelve 0. Inútil para descubrir por tema. |
| BCN buscador avanzado por fecha | 0 enlaces `idNorma`; el formulario necesita interacción real |
| CNE `/normativas/electricidad/` | redirige a **estudios**, no a normativa |
| CNE `/normativas/electrica/` | 884 chars, sin índice de normativa |
| CNE `/consulta-publica/electricidad/` | 4262 chars, pero son **datos y planillas**, no normativa |
| CEN `/normativas/` | 404 — la URL correcta no se encontró |
| SEC `/normativa/` | responde, 82 links, sin explorar a fondo |
| Diario Oficial `?date=DD-MM-AAAA` | el día ACTUAL carga; los días pasados devuelven 0-743 chars sin contenido |
| Diario Oficial PDF `/publicaciones/AAAA/MM/DD/sumarios/` | **403** |
| Diario Oficial datepicker (campo `dp`) | tras varios pedidos: `ERR_CONNECTION_RESET` y luego `chrome-error` — **bloqueo activo** |

## Lo que SÍ quedó establecido

**La sección correcta del Diario Oficial existe y es exactamente la necesaria:**
```
NORMAS GENERALES = "LEYES, REGLAMENTOS, DECRETOS Y RESOLUCIONES DE ORDEN GENERAL"
```
Y hay una ruta de PDF por fecha (`/publicaciones/AAAA/MM/DD/sumarios/<archivo>.pdf`), pero el
nombre del archivo no se pudo obtener: el día que cargaba era **domingo**, sin edición, así que
el enlace venía vacío (`sumarios/.pdf`).

**Vía no agotada:** obtener el nombre real del PDF desde un día hábil que sí cargue, y
comprobar si ese PDF es accesible por URL directa. Si lo fuera, el crawler baja de ~5 h a ~2 h.
El bloqueo obliga a espaciar los pedidos (≥60 s) y probablemente a rotar contexto de navegador.

## Prioridad, derivada de los datos (no de mi criterio)

Extraído del texto de la **LGSE** — quién tiene potestad normativa:
```
Ministerio de Energia   ->  decreto supremo · reglamento · resolucion
Comision (CNE)          ->  norma tecnica · reglamento · resolucion exenta
Superintendencia (SEC)  ->  resolucion exenta
Coordinador (CEN)       ->  resolucion exenta
```

Y del corpus, el núcleo de **mercados** (21 normas):
```
11 de 21 son DECRETO  (supremos del Ministerio de Energia)
 9 de 21 son LEY
 1 de 21 es RESOLUCION
```
Los decretos del núcleo son en buena parte de **actualización**: `ACTUALIZA VALORES`,
`EXTIENDE VIGENCIA`, `MODIFICA DS 62`, `MODIFICA DS 4T`. **La normativa tarifaria no se dicta y
queda quieta: se actualiza seguido.** Ese es el caso donde no enterarse cuesta caro.

⇒ Para mercados, la fuente que más cubre es el **Diario Oficial** (decretos supremos), no los
sitios de organismo. CNE importa para la NTCO (operación diaria), no para tarifas.

## Siguiente intento, cuando se retome
1. Cargar un día HÁBIL del Diario Oficial con espera larga y contexto nuevo.
2. Extraer el nombre real del PDF de sumario.
3. Probar acceso directo a ese PDF por URL.
4. Si funciona: parsear la sección NORMAS GENERALES y filtrar por dominio con el clasificador
   que ya existe (`frontera_mercados.DOMINIO`, corte 0.30 por articulado).

---

## 2026-08-24 — vía que SÍ funciona: descubrimiento por USO

Las 10 vías anteriores preguntaban *"¿qué normas existen?"* a buscadores y catálogos, y los
sitios bloquean. Esta pregunta otra cosa: **¿qué normas cita la gente que está litigando?**

Fuente: discrepancias y dictámenes ante el **Panel de Expertos** (`panelexpertos.cl`,
`cartas.coordinador.cl`). Son PDF públicos, se bajan con `curl` sin bloqueo y se leen con
`pdftotext -layout`. Script: `scripts/extraer_de_discrepancias.py`.

Por qué es mejor fuente que un buscador: una norma que aparece en una discrepancia real es
**normativa viva** — alguien la está usando para litigar hoy. Un resultado de búsqueda sólo
prueba que la norma existe.

**Primera pasada, 3 documentos (51.408 palabras):**
```
DECRETO 44    5 citas   Reglamento del Panel de Expertos
DECRETO 88    4 citas   Reglamento para Medios de Generación de Pequeña Escala
DECRETO 97    1 cita
DECRETO 244   1 cita
DECRETO 8810  1 cita    (el número viene pegado por el PDF; probablemente DECRETO 88)
```
Con **tres** documentos ya aparecen 5 normas que el corpus no tiene. Escala sola: más PDF en
`data/discrepancias/` y volver a correr.

**Segundo uso, gratis:** el mismo documento trae el planteamiento en lenguaje del sector **y**
el artículo exacto en que se apoya, citado por el abogado que lo redactó. Eso es un par
pregunta–gold que **no fabriqué yo**, que es justo lo que le falta a la FASE 3.2.

⚠️ Trampa del formato: `pdftotext -layout` pega numeraciones de línea al número de la norma
(`Decreto N°44.` + `1` → `DECRETO 441`; `Nº88` + `10` → `DECRETO 8810`). El corte por punto
sólo se aplica cuando lo que sigue no son 3 dígitos, porque el separador de miles chileno
agrupa siempre de a 3: `20.936` es 20936, pero `44.1` es 44. Lo que queda dudoso se **señala**
y no se corrige solo: resolver por truncamiento sesgaría el reporte hacia *"ya lo tenemos"*.
