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
