# Brief T14 — Scorer de precisión de dominio

Contrato: [`contrato.md`](contrato.md) · Spec: `docs/specs/cambios_dia-h1-reconocer-lo-nuevo.md`
· Cubre H1-CA-37, 38.

## Objetivo

Un script que, dado el conjunto etiquetado y los puntajes de una corrida, entregue la
precisión de la clase "en dominio" y las normas en dominio que cayeron fuera, por partición.

## Archivos

- Crear `scripts/puntuar_dominio.py`
- Crear `tests/descubrimiento/test_puntuar_dominio.py`

Ningún otro archivo. El conjunto etiquetado real todavía no existe: los tests usan datos
inventados en `tmp_path`.

## Qué hacer

1. Formatos de entrada: sección 4b del contrato.
2. Función pura `puntuar(etiquetado: list[dict], puntajes: list[dict]) -> dict` que devuelve,
   por cada partición presente (`dev`, `heldout`):
   - `clasificadas_en_dominio`, `en_dominio_correctas`,
   - `precision` = correctas / clasificadas en dominio (`None` si el denominador es 0),
   - `en_dominio_caidas_fuera`: lista de `id_norma` etiquetados `en_dominio` y clasificados
     `fuera_de_dominio`,
   - `dudosas`, `sin_puntaje`, `total`.
3. **Cómo se puntúa cada caso** (escribirlo también en el docstring del módulo, antes del
   código):
   - `dudosa` no cuenta como acierto ni como error en la precisión; se informa aparte.
   - sin puntaje (`clase` null, o norma etiquetada que no aparece en los puntajes) se
     excluye de la precisión y se cuenta en `sin_puntaje`.
   - una norma con puntaje que no está en el etiquetado se ignora y se cuenta en
     `no_etiquetadas` (a nivel raíz del resultado).
4. `main()` con `--etiquetado`, `--puntajes`, `--salida` (JSON). Imprime una tabla por
   partición y escribe el JSON con el resultado **y** con el detalle por norma (etiqueta,
   puntaje, clase), para poder re-auditar sin volver a calcular.
5. Código de salida 0 siempre que pueda calcular; el script informa, no decide si se
   cumple el umbral.

## Tests

Con datos inventados y resultados calculados a mano en el propio test:

- Caso base: 4 en dominio clasificadas en dominio, 1 fuera clasificada en dominio →
  precisión 0.8.
- Una `dudosa` etiquetada en dominio y otra etiquetada fuera: no cambian la precisión y
  `dudosas == 2`.
- Una etiquetada `en_dominio` clasificada `fuera_de_dominio`: aparece en
  `en_dominio_caidas_fuera`.
- Norma etiquetada ausente de los puntajes y norma con `clase` null: ambas en
  `sin_puntaje`.
- Ninguna clasificada en dominio: `precision is None`, sin división por cero.
- `dev` y `heldout` se calculan por separado y no se mezclan.
- `main()` escribe un JSON que incluye el detalle por norma.

## Terminado cuando

Los tests pasan con el entorno indicado.

## Fuera de alcance

Calcular puntajes, calibrar la zona dudosa, crear el conjunto etiquetado, usar GPU o la
base de datos.

## Entorno

`PYTHONPATH=. /home/alonso/.claude/jobs/6224a57d/tmp/venv/bin/python -m pytest tests/descubrimiento/test_puntuar_dominio.py -q`
(si `tests/conftest.py` impide la colección por falta de un paquete, repórtalo; no lo edites).
