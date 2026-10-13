# Contrato — Historia 1 (reconocer lo nuevo en BCN)

Lo que comparten todas las tareas de
[`docs/specs/cambios_dia-h1-tareas.md`](../specs/cambios_dia-h1-tareas.md). Un brief puede
restringir este contrato, nunca contradecirlo. Si una tarea necesita cambiarlo, se detiene
y lo reporta.

## 1. Reglas

1. Solo se tocan los archivos que el brief lista. Nada de `src/pipelines/retrieve.py`,
   `generate.py` ni el resto del pipeline del RAG.
2. Ninguna tarea inserta ni modifica filas de `normas` ni de `articulos`.
3. Ningún test hace peticiones de red. Los tests usan fixtures de `tests/fixtures/bcn/`.
4. Ninguna tarea hace peticiones a BCN. Los fixtures reales los captura quien coordina.
5. Sin dependencias nuevas: biblioteca estándar y lo que ya está en `requirements.txt`.
6. Ninguna lista de palabras ni regex decide dominio, intención u organismo como mecanismo
   principal (orden: dato → modelo → estructura → regla). Un regex para **extraer** un campo
   de un formato fijo sí se permite.
7. Ninguna tarea carga GPU salvo que su brief lo diga, y entonces pasa por
   `scripts/gpu_guard.sh`.
8. Código, nombres y comentarios en español, al estilo de `scripts/monitor_*.py`.
9. Commits con mensaje `tipo: descripción` en español. No se hace merge ni push a `main`.

## 2. Dónde vive el código

| Qué | Ruta |
|---|---|
| Lógica de la historia | paquete `src/descubrimiento/` (con `__init__.py`) |
| Scripts ejecutables | `scripts/` (uno por comando) |
| Tests | `tests/descubrimiento/` (con `__init__.py`) |
| Fixtures de BCN | `tests/fixtures/bcn/` |
| Conjunto etiquetado y calibración | `data/eval/dominio/` |

## 3. Tipos compartidos (`src/descubrimiento/tipos.py`)

Dataclasses congeladas. El archivo **ya existe** en la rama base; las tareas lo importan y
no lo modifican.

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Publicacion:
    """Una norma tal como la entrega un listado de BCN."""
    id_norma: str
    tipo: str                 # "LEY", "DECRETO", "DFL", "DL", "RESOLUCION", ...
    numero: str
    titulo: str
    organismos: tuple[str, ...]   # texto crudo de BCN, sin normalizar
    fecha_publicacion: str | None  # ISO AAAA-MM-DD
    url: str


@dataclass(frozen=True)
class Vinculacion:
    """Norma de origen que modifica o deroga a una norma del corpus."""
    id_norma_origen: str
    id_norma_afectada: str
    relacion: str             # "modifica" | "deroga"


@dataclass(frozen=True)
class Hallazgo:
    """Una norma nueva vista por una vía, antes de fusionar."""
    publicacion: Publicacion
    via: str                  # "V" | "O"
    afecta: tuple[Vinculacion, ...] = field(default_factory=tuple)
```

`url` es siempre `https://www.bcn.cl/leychile/navegar?idNorma=<id_norma>`.
`id_norma` es siempre `str`.

## 4. Base de datos

Tablas nuevas, creadas por DDL idempotente en `scripts/descubrimiento_schema.py` (mismo
estilo que `scripts/monitor_schema.py`; no se agrega migración de alembic).

`norma_candidata` — una fila por norma nueva reconocida:

| Columna | Tipo | Nota |
|---|---|---|
| `id_norma` | text PK | llave de identidad |
| `tipo`, `numero`, `titulo` | text | |
| `organismos` | jsonb | lista de textos crudos |
| `organismo_normalizado` | text | puede ser null |
| `fecha_publicacion` | date | puede ser null |
| `url` | text | |
| `vias` | jsonb | lista: `["V"]`, `["O"]` o ambas |
| `afecta` | jsonb | lista de `{id_norma, relacion}` |
| `estado` | text | `pendiente`, `aprobada`, `rechazada`, `fallo_identidad` |
| `puntaje_dominio` | double precision | null = no disponible |
| `alcanza_corte` | boolean | null si no hay puntaje |
| `clase_dominio` | text | `en_dominio`, `dudosa`, `fuera_de_dominio` o null |
| `relevante_por_vinculacion` | boolean | default false |
| `embedder`, `version_referencia` | text | con qué se calculó el puntaje |
| `detectada_en` | timestamptz | default `now()` |

`descubrimiento_corrida` — una fila por corrida:

| Columna | Tipo | Nota |
|---|---|---|
| `id` | bigserial PK | |
| `inicio`, `fin` | timestamptz | `fin` null = no terminó |
| `ventana_desde`, `ventana_hasta` | date | |
| `exitosa` | boolean | default false |
| `detalle` | jsonb | por vía: revisadas, candidatas, no_revisadas, completa; conteo por clase |

Conexión: `from src.storage.connection import with_connection`.

## 4b. Archivos de datos de dominio

JSONL, una norma por línea, en `data/eval/dominio/`:

- `etiquetado.jsonl` — `{"id_norma", "tipo", "numero", "titulo", "etiqueta", "motivo",
  "particion"}` con `etiqueta` en `en_dominio` | `fuera_de_dominio` y `particion` en
  `dev` | `heldout`.
- puntajes de una corrida — `{"id_norma", "puntaje", "clase"}`; `puntaje` y `clase` pueden
  ser null (sin puntaje); `clase` en `en_dominio` | `dudosa` | `fuera_de_dominio`.

## 5. Red

Todo acceso a red pasa por `src/descubrimiento/cliente_bcn.py`. Hosts permitidos:
`bcn.cl`, `www.bcn.cl`, `leychile.cl`, `www.leychile.cl`, `localhost`, `127.0.0.1`.
Intervalo mínimo entre peticiones: 20 s, configurable. BCN exige `User-Agent` de navegador.

## 6. Tests

- Se corren con el entorno que indique el brief, desde la raíz del worktree, con
  `PYTHONPATH=.`.
- Los tests que necesitan Postgres llevan `@pytest.mark.integration` y usan el fixture
  `db_clean` de `tests/conftest.py`.
- El reporte final dice qué tests se corrieron, cuáles pasaron y cuáles **no se pudieron
  correr** y por qué. No se declara terminado algo que no se ejecutó.

## 7. Reporte al terminar

Rama, commits, archivos tocados, salida de los tests, criterios `H1-CA-xx` cubiertos, y
toda decisión que el brief no cubría.
