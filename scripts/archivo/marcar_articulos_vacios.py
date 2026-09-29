"""Marca como `fantasma` los articulos casi vacios que el buscador todavia puede devolver.

ORIGEN (2026-09-17): tras aplicar `scripts/limpiar_notas_bcn.py --apply` (#69a), la limpieza
dejo filas cuyo cuerpo ya estaba roto ANTES por la segmentacion vieja y de las que la nota era
casi todo el contenido:

    "- Los precios |D.F.L. Nº 1, de 1982, Minería|"  (43 chars) -> "- Los precios"  (13 chars)

Medido despues de la limpieza:
    8 articulos quedaron VACIOS          (5 ya marcados fantasma, 3 visibles)
    341 articulos con < 60 chars         (127 fantasma, 66 derogados, 148 VISIBLES)
    149 de esos visibles tienen fragmentos indexados -> son recuperables

La regla `fantasma` de #69b no los cubre: ahi un fantasma era una fila cuyo texto vivia en otra
fila. Aca el texto no vive en ningun lado, simplemente no hay articulo.

QUE HACE: pone `metadata.fantasma = '78-vacio'`, que es lo que `vectorstore.py` ya filtra en sus
3 consultas. NO borra nada, NO toca el texto.

CRITERIO, FIJADO ANTES DE CORRER (regla del proyecto):
    adoptar si   cita_ok NO cae > 3  Y  cita_limpia NO cae     en dev Y held-out
    contra       limpio2_dev / limpio2_holdout (la DB ya limpia, NO qonly2_*)
    cae en cualquiera de los dos                               -> --revertir
Prediccion registrada: cita_ok no deberia moverse (estos articulos no son gold de ninguna query
del set); lo que puede mejorar es la PRECISION, al dejar de ocupar un lugar del top-k con una
fila de 13 chars. Si cita_ok SUBE mucho, sospechar: seria senal de que el umbral esta botando
articulos reales.

UMBRAL: `MIN_CHARS` (default 60) es el mismo corte que ya usa el diagnostico de #69b
("articulos < 60 chars: 486 -> 152"), no un numero nuevo inventado aca.

Uso:  env PYTHONPATH=. venv/bin/python -m scripts.archivo.marcar_articulos_vacios
      (sin --apply solo informa; con --apply marca y respalda; --revertir deshace)
"""
import os
import sys

from src.storage.connection import with_connection

SUF = "_bak_vacios_20260917"
MARCA = "78-vacio"
MIN_CHARS = int(os.environ.get("MIN_CHARS", "60"))
APPLY = "--apply" in sys.argv
REVERT = "--revertir" in sys.argv

# Solo los VISIBLES: si ya es fantasma o derogado, el buscador no lo devuelve y no hay nada
# que arreglar. Se excluyen los derogados a proposito: "(DEROGADO)" es contenido legitimo y
# corto, y marcarlo fantasma seria esconder informacion real.
SEL = f"""
    SELECT id, id_norma, numero, length(texto) AS n, texto
      FROM articulos
     WHERE length(coalesce(texto, '')) < {MIN_CHARS}
       AND (metadata->>'fantasma') IS NULL
       AND coalesce(derogado, false) = false
     ORDER BY n
"""


def revertir(cur):
    cur.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name = 'articulos{SUF}'")
    if not cur.fetchone()[0]:
        print(f"no existe articulos{SUF}: nada que revertir")
        return
    cur.execute(
        f"UPDATE articulos a SET metadata = b.metadata FROM articulos{SUF} b WHERE b.id = a.id"
    )
    print(f"  revertido: {cur.rowcount} articulos vuelven a su metadata previa")


def main():
    with with_connection() as conn:
        cur = conn.cursor()
        if REVERT:
            revertir(cur)
            conn.commit()
            return

        cur.execute(SEL)
        filas = cur.fetchall()
        vacios = [f for f in filas if f[3] == 0]
        print(f"articulos visibles con < {MIN_CHARS} chars: {len(filas)}  (de ellos vacios: {len(vacios)})")

        # Cuantos son realmente alcanzables: sin fragmentos indexados el retrieval no los ve.
        ids = [f[0] for f in filas]
        if ids:
            cur.execute(
                "SELECT count(DISTINCT articulo_id) FROM fragmentos WHERE articulo_id = ANY(%s)",
                (ids,),
            )
            print(f"  con fragmentos indexados (recuperables hoy): {cur.fetchone()[0]}")

        print("\n  muestra (los 10 mas cortos):")
        for _id, norma, num, n, txt in filas[:10]:
            print(f"    {norma}/{num:<12} {n:>3} chars  {(txt or '')[:70]!r}")

        if not APPLY:
            print("\n(sin --apply no se toca nada)")
            return

        cur.execute(f"DROP TABLE IF EXISTS articulos{SUF}")
        cur.execute(
            f"CREATE TABLE articulos{SUF} AS SELECT id, metadata FROM articulos WHERE id = ANY(%s)",
            (ids,),
        )
        cur.execute(
            "UPDATE articulos SET metadata = coalesce(metadata, '{}'::jsonb) || %s::jsonb "
            "WHERE id = ANY(%s)",
            (f'{{"fantasma": "{MARCA}"}}', ids),
        )
        print(f"\n  marcados {cur.rowcount} articulos con fantasma='{MARCA}', respaldo en articulos{SUF}")
        conn.commit()


if __name__ == "__main__":
    main()
