"""ETAPA B de #69a: re-embeber EN SITIO las 1120 filas cuyo texto limpio la etapa A.

POR QUE (medido 2026-09-17): `limpiar_notas_bcn.py --apply` limpio `fragmentos.text` y
`contextual_text`, y el `tsv` de BM25 se recalculo solo (es GENERATED). Los VECTORES no.
Resultado: BM25 lee el texto nuevo y el denso el viejo -> los dos generadores de candidatos
quedan desincronizados y el orden del pool baila.

Se vio en el eval: dev cita_limpia 80 -> 79 con 5 ganadas y 6 perdidas (revoloteo, p=1.0), y
las 6 perdidas NO son de etiqueta sino de retrieval (trae otro articulo). Held-out, donde el
efecto de etiqueta manda, gano 4 y perdio 0.

QUE HACE: para cada fragmento tocado, recalcula
    embedding_4b_1024  <- 4B (GGUF Ollama) sobre el contextual_text LIMPIO, prefijo MRL 1024,
                          normalizado L2   <- ES LA COLUMNA QUE USA PRODUCCION (6583/6583)
    embedding          <- Qwen3-Embedding-0.6B sobre el mismo texto
Misma receta que `scripts/reparar_articulos.py::refragmentar` (lineas 186-191), para no
inventar una variante distinta de la que ya esta en la DB.

NO re-fragmenta (los chunks no cambian: solo se les quito la nota) y NO toca
`fragmentos_inciso` (experimental, igual que #69b).

CRITERIO, FIJADO ANTES DE CORRER:
    adoptar si   cita_ok NO cae > 3  Y  cita_limpia NO cae     dev Y held-out
    contra       qonly2_dev / qonly2_holdout (la DB SUCIA, el baseline de siempre)
    cae          -> revertir ETAPA A completa (limpiar_notas_bcn.py --revertir)
PREDICCION REGISTRADA: si la hipotesis del desajuste es correcta, dev deja de perder las 6 de
retrieval y cita_limpia vuelve a >= 80; held-out conserva sus 4 ganadas. Si dev sigue en 79,
la hipotesis era falsa y la limpieza NO se adopta.

Uso:  env PYTHONPATH=. venv/bin/python -m scripts.reembeber_limpiados [--apply]
      sin --apply solo informa.  --revertir restaura los vectores viejos.
"""
import math
import sys

from src.storage.connection import with_connection

ORIG = "fragmentos_bak_notas_20260906"   # respaldo de la etapa A: de aqui salen los ids
SUF = "_bak_emb_20260917"                 # respaldo de los vectores VIEJOS (esta etapa)
APPLY = "--apply" in sys.argv
REVERT = "--revertir" in sys.argv


def revertir(cur):
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = %s",
                (f"fragmentos{SUF}",))
    if not cur.fetchone()[0]:
        print(f"no existe fragmentos{SUF}: nada que revertir")
        return
    cur.execute(f"""UPDATE fragmentos f SET embedding = b.embedding,
                           embedding_4b_1024 = b.embedding_4b_1024
                      FROM fragmentos{SUF} b WHERE b.id = f.id""")
    print(f"  revertido: {cur.rowcount} fragmentos vuelven a sus vectores previos")


def main():
    with with_connection() as conn:
        cur = conn.cursor()
        if REVERT:
            revertir(cur)
            conn.commit()
            return

        cur.execute(f"""SELECT f.id, f.contextual_text
                          FROM fragmentos f JOIN {ORIG} b ON b.id = f.id
                         WHERE f.contextual_text IS NOT NULL
                         ORDER BY f.id""")
        filas = cur.fetchall()
        print(f"fragmentos a re-embeber: {len(filas)}")
        if not APPLY:
            print("(sin --apply no se toca nada)")
            return

        from src.components.embedder import Qwen3Embedder
        from src.pipelines.retrieve import _embed_4b_query

        emb06 = Qwen3Embedder()
        ids = [f[0] for f in filas]
        cur.execute(f"DROP TABLE IF EXISTS fragmentos{SUF}")
        cur.execute(f"""CREATE TABLE fragmentos{SUF} AS
                        SELECT id, embedding, embedding_4b_1024 FROM fragmentos
                         WHERE id = ANY(%s)""", (ids,))
        print(f"  respaldo de vectores viejos en fragmentos{SUF}")

        hechos = fallos = 0
        for i, (fid, ctx) in enumerate(filas, 1):
            e4 = _embed_4b_query(ctx) or []
            s4 = e4[:1024]
            if not s4:
                fallos += 1
                continue
            nn = math.sqrt(sum(x * x for x in s4)) or 1.0
            cur.execute("UPDATE fragmentos SET embedding = %s, embedding_4b_1024 = %s WHERE id = %s",
                        (emb06.embed([ctx])[0], [x / nn for x in s4], fid))
            hechos += 1
            if i % 100 == 0:
                conn.commit()
                print(f"  [{i}/{len(filas)}]", flush=True)
        conn.commit()
        print(f"  re-embebidos {hechos}, sin vector 4B {fallos}")


if __name__ == "__main__":
    main()
