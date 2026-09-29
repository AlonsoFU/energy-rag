# Modelo de datos: conceptos, definiciones y aristas (con ejemplos literales)

> Doc de referencia para entender el vocabulario del sistema y la diferencia
> entre **concepto** y **definición**. Todos los ejemplos son datos REALES de
> la DB (no inventados), para poder revisarlos en el futuro.
> Creado 2026-05-26.

---

## Glosario de términos (qué significa cada palabra que usamos)

| Término | Qué es | Dónde vive en la DB |
|---|---|---|
| **concepto** | LA PALABRA / el término que se define. Un nodo, una entrada. | fila en `conceptos` (`id`, `nombre`, `aliases`, `definicion`) |
| **definición** | EL TEXTO que explica qué significa el concepto. | dos lugares (ver abajo) |
| **glosario** | la colección de definiciones (el "diccionario" entero). | el texto de `conceptos.definicion` proviene del glosario |
| **aliases** | otras formas de nombrar el concepto (siglas, variantes). Opcional por-concepto, pero importante como campo. | `conceptos.aliases` (puede ser `None`) |
| **norma** | el documento legal (ley, decreto, resolución). Un "libro". | fila en `normas` (`id_norma`, `tipo`, `titulo`, `fecha_publicacion`) |
| **artículo** | una sección de la norma. Una "página". | fila en `articulos` (`id_norma`, `numero`, `texto`) |
| **arista** | el enlace `artículo ──► concepto`. | fila en `referencias` (`tipo_relacion`) |
| **define_termino** | tipo de arista: "aquí se DEFINE el término". | `referencias.tipo_relacion = 'define_termino'` |
| **cita** | tipo de arista: "aquí solo se MENCIONA / usa el término". | `referencias.tipo_relacion = 'cita'` |

### La diferencia clave: concepto ≠ definición

Como en un diccionario:

```
  CONCEPTO   →  "perro"                          (la entrada, la palabra)
  DEFINICIÓN →  "mamífero canino doméstico…"     (lo que significa)
```

- **concepto** = *la palabra* que se define. Es un nodo.
- **definición** = *el texto que explica qué es* esa palabra.

### Las DOS definiciones (la sutileza que confunde)

La definición vive en dos lugares, y el sistema responde apuntando al #2:

| | Dónde | Rol |
|---|---|---|
| **1. Definición de glosario** | columna `conceptos.definicion` | resumen guardado sobre el concepto |
| **2. Definición legal (la fuente)** | el **artículo** al que llega la arista `define_termino` | la **fuente oficial citable** |

---

## Ejemplo limpio: "Suficiencia de Potencia" (concepto id 114)

Datos reales de la DB.

```
CONCEPTO (tabla `conceptos`, id=114)
  nombre    = "Suficiencia de Potencia"      ← LA PALABRA (el qué)
  aliases   = None                            ← sin variantes (opcional)
  definicion= "Capacidad de un sistema o subsistema para abastecer la
               Demanda de Punta, considerando…"   ← QUÉ SIGNIFICA (glosario)

NORMA 250604 = DECRETO 62 "Reglamento de Transferencias de Potencia" (2006)   ← el "libro"
ARTÍCULO 250604/art13 = "Artículo 13: …se entenderá por: … Suficiencia de
                         Potencia:…"                                          ← la "página"
```

Grafo real de este concepto (sus aristas):

```
                            ┌─ define_termino ─►  250604 / art13   ← aquí lo DEFINE (fuente)
   "Suficiencia de Potencia"┤
        (concepto 114)      ├─ cita ───────────►  250604 / art13   ← (mismo art, también citado)
                            ├─ cita ───────────►  250604 / art56   ← lo menciona
                            └─ cita ───────────►  1204012 / primero ← lo menciona
```

---

## Ejemplo del BUG de deduplicación: "Escenario Energético" (concepto id 267)

Caso real que diagnosticamos. El gold (la respuesta correcta) es **1160108/art2**.

Aristas reales (tabla `referencias`):

```
ref#4917  define_termino  1112591/art2°    ← RESOLUCIÓN 711 (2017, rango 1) lo DEFINE
ref#1383  cita            1112591/art2°
ref#4755  define_termino  1160108/art2     ← DECRETO 37 (2021, rango 2) lo DEFINE   ┐ MISMO
ref#2234  cita            1160108/art2     ← DECRETO 37 lo nombra                   ┘ artículo
ref#2472  cita            1160108/art83    ← DECRETO 37 lo usa
ref#1414  cita            1112591/art11°
```

Las aristas están BIEN: el gold (1160108/art2) existe como `define_termino`.

### Dónde se rompe

```
SQL trae las filas (ordenadas por norma/artículo, NO por tipo de arista)
        │
        ▼
build_candidates()  →  deduplica por (norma, artículo), se queda con la 1ª fila
        │
        │   para 1160108/art2 llegan DOS filas:
        │        cita            ◄── viene primero  →  SE QUEDA con esta
        │        define_termino  ◄── llega después  →  DESCARTADA   ✗✗✗  ←★ EL ERROR
        ▼
candidatos:
        1112591/art2°   origin = curated   ✔
        1160108/art2    origin = cita      ✗  ← debería ser "curated" (¡es el gold!)
        │
        ▼
Capa 1 (solo confía en curated = define_termino)
        curated = [ 1112591/art2° ]        ← el gold quedó afuera
        → único candidato → resuelve  1112591/art2°   ✗  (mal)

        gold correcto = 1160108/art2
```

### El fix (verificado en memoria)

`build_candidates` debe hacer que, para el mismo artículo, **`define_termino` gane a `cita`**.
Con eso entran las dos definiciones reales y Capa 1 decide por jerarquía→fecha:

```
curated = [ 1112591/art2° (rango 1, 2017),  1160108/art2 (rango 2, 2021) ]
Capa 1 → jerarquía: DECRETO 2021 > RESOLUCIÓN 2017 → 1160108/art2  ✔ = GOLD, alta confianza
```

**En una línea:** el error no está en las aristas (están bien) ni en las capas del
resolver (la regla jerarquía→fecha funciona) — está en el paso intermedio que las
junta: al colapsar el artículo con `cita` + `define_termino`, se queda con la etiqueta
equivocada (`cita`) y esconde la definición real de la capa confiable.

---

## ¿Es suficiente este grafo para GraphRAG?

**Hoy: no del todo.**

- **Sirve para** "qué es X" → un salto `concepto → artículo de definición`. RAG definicional. ✔
- **GraphRAG de verdad** necesita preguntas multi-salto relacionales
  ("¿qué organismo fiscaliza las concesiones que otorga el Ministerio?"). Para eso
  faltan tipos de arista que casi no existen:
  - **concepto → concepto** (relaciones entre entidades, no solo "se define en"),
  - **norma → norma** (deroga / modifica / remite — p.ej. AVI art48 remite a arts 104/118 LGSE),
  - la **capa de valores** (decretos que fijan montos) y el **ámbito/contexto**.
- El grafo actual es casi todo **concepto↔artículo** (definir/mencionar): buen primer
  piso, pero le falta estructura relacional. GraphRAG **amplifica** lo que el grafo ya
  tiene (bueno y malo) → conviene arreglar dedup + ruido de extracción antes.
