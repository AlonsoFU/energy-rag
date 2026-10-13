# Brief T04 — Leer el listado de publicaciones de BCN

Contrato: [`contrato.md`](contrato.md) · Spec: `docs/specs/cambios_dia-h1-reconocer-lo-nuevo.md`
· Cubre H1-CA-08 (parte) y H1-CA-11.

## Objetivo

Convertir el XML de `obtxml?opt=3` en una lista de `Publicacion`.

## Archivos

- Crear `src/descubrimiento/listado.py`
- Crear `tests/descubrimiento/test_listado.py`
- Leer (no modificar) `tests/fixtures/bcn/obtxml_opt3_cantidad20.xml` y
  `src/descubrimiento/tipos.py`

Ningún otro archivo.

## Qué hacer

1. Función `leer_listado(xml: bytes) -> list[Publicacion]` con `xml.etree.ElementTree`.
2. Estructura real del XML (fixture capturado el 2026-10-13, 20 normas, todas leyes):
   `NORMAS > NORMA[@idNorma]` con `TIPOS_NUMEROS/TIPO_NUMERO/{TIPO, NUMERO, DESCRIPCION,
   COMPUESTO}`, `FECHA_PUBLICACION`, `FECHA_PROMULGACION`, `TITULO`,
   `ORGANISMOS/ORGANISMO` (puede haber más de uno) y `TEXTO`.
3. Mapeo:
   - `id_norma` ← atributo `idNorma`.
   - `tipo` ← `DESCRIPCION` del primer `TIPO_NUMERO`, en mayúsculas y sin tildes
     (`Ley` → `LEY`, `Resolución` → `RESOLUCION`). No traducir con una tabla de códigos
     `XX1`: se usa el texto que entrega BCN.
   - `numero` ← `NUMERO` del primer `TIPO_NUMERO`.
   - `titulo` ← `TITULO` con espacios colapsados.
   - `organismos` ← todos los `ORGANISMO`, texto crudo recortado, en orden.
   - `fecha_publicacion` ← `FECHA_PUBLICACION`, o `None` si falta o viene vacía.
   - `url` ← la del contrato.
4. Una `NORMA` sin `idNorma` se omite y se cuenta: `leer_listado` no falla por una entrada
   mala. Exponer `leer_listado_con_descartes(xml) -> (list[Publicacion], int)` y que
   `leer_listado` la use.
5. XML que no parsea: lanzar `ValueError` con un mensaje claro.

## Tests

- El fixture real devuelve 20 publicaciones, todas con `id_norma`, `tipo == "LEY"`,
  `numero`, `titulo`, al menos un organismo, fecha ISO y la URL correcta.
- La primera del fixture es `id_norma="1228972"`, número `21841`, organismo
  `MINISTERIO DE OBRAS PÚBLICAS`, fecha `2026-10-09`.
- XML sintético con dos organismos: salen ambos en orden.
- XML sintético con una norma sin `idNorma` y otra válida: una publicación, un descarte.
- XML sintético sin `FECHA_PUBLICACION`: `fecha_publicacion is None`.
- Bytes que no son XML: `ValueError`.

## Terminado cuando

Los tests pasan con el entorno indicado.

## Fuera de alcance

Filtrar por organismo o por fecha, normalizar organismos, descargar el listado, tocar la
base de datos.

## Entorno

`PYTHONPATH=. /home/alonso/.claude/jobs/6224a57d/tmp/venv/bin/python -m pytest tests/descubrimiento/test_listado.py -q`
(si `tests/conftest.py` impide la colección por falta de un paquete, repórtalo; no lo edites).
