"""B3/0.2 — clasificar las normas candidatas por cercanía a la SUBGERENCIA DE MERCADOS.

El usuario definió la frontera (2026-08-22): *"el corpus es todo lo referente a la
subgerencia de mercados"*. Esto la vuelve operable **sin inventar una lista de materias**:

- NO se usa un regex de palabras clave (sería R1 del banco de reglas: una decisión de dominio
  del usuario disfrazada de heurística mía).
- NO se usa `normas.organismo`: el campo está CORRUPTO — 69 de 95 en NULL y el resto con
  texto arbitrario ("s.".", "de planificación competente."), porque el parser lo extrae con
  `MINISTERIO DE ([A-ZÁÉÍÓÚÑ\\s,]+?)` y agarra cualquier cosa.
- SÍ se usa el mismo embedder del retrieval (`qwen3-embedding:4b`, MRL-1024) comparando el
  TÍTULO de cada norma contra una descripción del dominio, y **la descripción sale de las
  funciones reales de la subgerencia**, no de mi criterio.

La salida es un ranking para que el usuario VALIDE, no una decisión automática. El corte lo
pone él; acá solo se ordena por evidencia (cercanía semántica × veces citada desde el dominio).

  PYTHONPATH=. venv/bin/python -m scripts.frontera_mercados
"""
import json
import math
import re
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.pipelines.retrieve import _embed_4b_query

# Funciones de la Subgerencia de Transferencias de Mercado del CEN. Es la DEFINICION DEL
# DOMINIO dada por el usuario, expandida a las materias que la subgerencia opera.
# No es una lista de filtrado: es el texto de referencia contra el que se mide similitud.
DOMINIO = """
Transferencias económicas entre empresas del sector eléctrico. Balance de inyecciones y
retiros de energía y potencia. Valorización de las transferencias. Informe de valorización
de transferencias económicas. Reliquidaciones. Peajes de transmisión nacional, zonal y
dedicada. Precios de nudo. Tarifas y remuneración de sistemas de transmisión. Potencia de
suficiencia y pago por capacidad. Servicios complementarios y su valorización. Costos
marginales. Clientes libres y clientes regulados. Coordinación de la operación del sistema
eléctrico nacional. Mercado eléctrico mayorista.
"""


def _norm_vec(t):
    v = _embed_4b_query(t)
    if not v:
        return None
    s = v[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def cos(a, b):
    return sum(x * y for x, y in zip(a, b))


def main():
    ref = _norm_vec(re.sub(r"\s+", " ", DOMINIO).strip())
    if not ref:
        print("ERROR: no se pudo embeber la descripcion del dominio"); return 1

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero, titulo FROM normas ORDER BY id_norma")
        dentro = cur.fetchall()

    print(f"=== normas YA en el corpus ({len(dentro)}) ordenadas por cercania al dominio ===",
          flush=True)
    filas = []
    for n in dentro:
        v = _norm_vec(str(n["titulo"] or "")[:400])
        filas.append((cos(ref, v) if v else -1.0, n))
    filas.sort(reverse=True, key=lambda x: x[0])

    print("\n-- MAS cercanas (nucleo del dominio)")
    for s, n in filas[:12]:
        print(f"   {s:.3f}  {n['tipo']:<10} {str(n['numero']):>6}  {str(n['titulo'])[:62]}")
    print("\n-- MENOS cercanas (candidatas a PODAR)")
    for s, n in filas[-15:]:
        print(f"   {s:.3f}  {n['tipo']:<10} {str(n['numero']):>6}  {str(n['titulo'])[:62]}")

    out = Path("docs/frontera-mercados.md")
    L = ["# Frontera del corpus — Subgerencia de Mercados", "",
         "Criterio del usuario (2026-08-22): *el corpus es todo lo referente a la subgerencia",
         "de mercados*. Acá se ordena por **cercanía semántica** del título a las funciones de",
         "la subgerencia, medida con el mismo embedder del retrieval.",
         "",
         "⚠️ **Esto NO decide nada**: es un ranking para que el usuario ponga el corte.",
         "No se usó lista de palabras clave (sería mi criterio, no el suyo) ni el campo",
         "`normas.organismo` (está corrupto: 69/95 en NULL y el resto con texto arbitrario).",
         "", "## Normas ya en el corpus", "",
         "| sim | tipo | número | título |", "|---|---|---|---|"]
    for s, n in filas:
        L.append(f"| {s:.3f} | {n['tipo']} | {n['numero']} | {str(n['titulo'])[:88]} |")
    out.write_text("\n".join(L) + "\n")
    print(f"\nescrito {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
