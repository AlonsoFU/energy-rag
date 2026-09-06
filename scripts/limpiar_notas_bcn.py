"""exp #69a -- quitar las notas de modificacion de BCN intercaladas en el texto (2026-09-06).

Hallazgo de exp #68: 881/4984 articulos traian notas tipo `Ley 20402 / Art. 10 Nº 1 /
D.O. 03.12.2009` dentro del texto, a veces partiendo una palabra. El generador las lee como
texto de la ley ("la Ley 20402 crea la SEC"). El limpiador del parser solo cazaba las que
traian organismo en mayusculas. Se extendio el parser (NOTA_BCN_*); esto aplica ESE limpiador
a lo ya indexado, sin re-chunkear ni re-embeber (etapa a). Etapa b = re-embeber lo tocado.

Toca, con respaldo previo en tablas *_bak_notas_20260906:
  articulos.texto
  fragmentos.text, fragmentos.contextual_text   (tsv es GENERATED -> se recalcula solo)
  fragmentos_inciso.text, .contextual_text, .tsv (tsv NO es generated -> se recalcula aca)
Los embeddings quedan como estan (etapa b). Las notas son ~5 % de los chars afectados.

Uso:  env PYTHONPATH=. venv/bin/python -m scripts.limpiar_notas_bcn [--apply]
Sin --apply solo informa. Reversible: scripts/limpiar_notas_bcn.py --revertir
"""
import sys
from src.parsers.norm_structure_parser import NormStructureParser
from src.storage.connection import with_connection

SUF = "_bak_notas_20260906"
APPLY = "--apply" in sys.argv
REVERT = "--revertir" in sys.argv
p = NormStructureParser()
PATS = (p.NOTA_BCN_PATTERN, p.NOTA_BCN_COLA_INICIO, p.NOTA_BCN_CABEZA_FIN, p.MODIFICACION_PATTERN)


def limpiar(v):
    """Solo toca filas con nota: el limpiador tambien normaliza espacios y eso inflaba el
    diff a 2236 articulos (881 tienen nota)."""
    if not any(pt.search(v) for pt in PATS):
        return v
    return p._limpiar_texto_articulo(v)


def revertir(cur):
    for t, cols in (("articulos", ["texto"]),
                    ("fragmentos", ["text", "contextual_text"]),
                    ("fragmentos_inciso", ["text", "contextual_text", "tsv"])):
        sets = ", ".join(f"{c}=b.{c}" for c in cols)
        cur.execute(f"UPDATE {t} x SET {sets} FROM {t}{SUF} b WHERE b.id=x.id")
        print(f"  revertido {t}: {cur.rowcount}")


def main():
    with with_connection() as conn:
        cur = conn.cursor()
        if REVERT:
            revertir(cur); conn.commit(); return
        plan = {}
        for t, cols in (("articulos", ["texto"]),
                        ("fragmentos", ["text", "contextual_text"]),
                        ("fragmentos_inciso", ["text", "contextual_text"])):
            cur.execute(f"SELECT id, {', '.join(cols)} FROM {t}")
            cambios = []
            for row in cur.fetchall():
                nuevos = [limpiar(v) if v else v for v in row[1:]]
                if any(n != v for n, v in zip(nuevos, row[1:])):
                    cambios.append((row[0], nuevos))
            plan[t] = (cols, cambios)
            print(f"{t}: {len(cambios)} filas cambian")
        if not APPLY:
            print("(sin --apply no se toca nada)"); return
        for t, (cols, cambios) in plan.items():
            extra = ", tsv" if t == "fragmentos_inciso" else ""
            cur.execute(f"DROP TABLE IF EXISTS {t}{SUF}")
            cur.execute(f"CREATE TABLE {t}{SUF} AS SELECT id, {', '.join(cols)}{extra} FROM {t} "
                        f"WHERE id = ANY(%s)", ([i for i, _ in cambios],))
            sets = ", ".join(f"{c}=%s" for c in cols)
            if t == "fragmentos_inciso":
                sets += ", tsv=to_tsvector('spanish', %s)"
            for i, nuevos in cambios:
                vals = list(nuevos) + ([nuevos[1] or nuevos[0]] if t == "fragmentos_inciso" else [])
                cur.execute(f"UPDATE {t} SET {sets} WHERE id=%s", (*vals, i))
            print(f"  {t}: aplicado {len(cambios)}, respaldo en {t}{SUF}")
        conn.commit()


if __name__ == "__main__":
    main()
