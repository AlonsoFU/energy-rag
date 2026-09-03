"""El grafo de relaciones esta inflado 2.1x: colapsar aristas repetidas guardando `veces`.

Hallazgo (2026-09-03): `referencias` guarda UNA FILA POR OCURRENCIA de la cita en el texto,
no una por arista. Una norma citada 15 veces dentro del mismo articulo son 15 filas identicas.
Medido:

    tipo                   filas  aristas unicas  inflado
    modifica                 379              92     4.1x
    deroga                    16               2     8.0x
    remite                  2206            1500     1.5x
    aplica                   175             156     1.1x
    cita                    3931            3931     1.0x
    define_termino           222             222     1.0x
    referencia_implicita     170             170     1.0x
    TOTAL                   7100            6074     1.2x

**El inflado esta concentrado en las relaciones norma->norma** (`modifica`, `deroga`,
`remite`), que son justo las que forman el mapa normativo. Las aristas a concepto
(`cita`, `define_termino`) no estan duplicadas.

Las 15 relaciones `deroga` a nivel articulo eran **la misma arista 15 veces**
(LEY 19882 -> LEY 18575 art 2°). La cobertura real de derogacion cruzada es 2 aristas, no 15.

⚠️ La primera medicion de esto dio 2.1x global y 17.1x en `define_termino`: agrupaba sin
`destino_concepto_id`, asi que todas las aristas a concepto caian en la misma clave. La clave
de identidad tiene que llevar los TRES destinos posibles, que es lo que hace `CLAVE` abajo.

⚠️ **Esto NO es un bug de retrieval.** El unico consumidor en la ruta de respuesta
(`src/pipelines/retrieve.py:288`) usa `any(...)` y `max(years)`, que son semantica de conjunto:
las filas repetidas no mueven el score. Verificado leyendo el consumidor antes de tocar nada.
Lo que si esta mal es TODO lo que cuenta relaciones: el mapa del corpus, `--impacto`, y
cualquier informe que diga "N relaciones".

La frecuencia NO se tira: se guarda en `veces`. Que una norma se cite 15 veces en un articulo
es senal (es la norma que ese articulo esta modificando), y perderla seria cambiar un error por
otro.

    venv/bin/python -m scripts.dedup_referencias            # dry-run, no escribe
    venv/bin/python -m scripts.dedup_referencias --aplicar  # colapsa

⚠️ NO correr con un experimento pareado en curso: cambia el corpus entre brazos.
"""
import sys
import psycopg
from psycopg.rows import dict_row
from src.core import config as cfg

# La identidad de una arista. `contexto` NO entra: es el texto que rodea a ESA ocurrencia y
# difiere entre filas que son la misma relacion. Al colapsar se conserva el contexto mas largo,
# que es el que mas informacion da para auditar.
CLAVE = ("origen_articulo_id", "destino_articulo_id", "destino_norma_id",
         "destino_concepto_id", "tipo_relacion")


def main(aplicar=False):
    with psycopg.connect(cfg.settings.dsn()) as cn, cn.cursor(row_factory=dict_row) as cur:
        cur.execute("select count(*) n from referencias")
        antes = cur.fetchone()["n"]
        k = ", ".join(CLAVE)
        cur.execute(f"select count(*) n from (select 1 from referencias group by {k}) t")
        unicas = cur.fetchone()["n"]
        print(f"filas {antes}  ->  aristas unicas {unicas}   (inflado {antes/unicas:.1f}x)")

        cur.execute(f"""select tipo_relacion, count(*) filas,
                               count(distinct ({k})) aristas
                        from referencias group by 1 order by 2 desc""")
        for r in cur.fetchall():
            infl = r["filas"] / r["aristas"] if r["aristas"] else 0
            print(f"  {str(r['tipo_relacion']):22} {r['filas']:>6} -> {r['aristas']:>6}  {infl:>5.1f}x")

        if not aplicar:
            print("\n(dry-run: no se escribio nada. --aplicar para colapsar)")
            return

        cur.execute("alter table referencias add column if not exists veces integer default 1")
        # Colapsa en una tabla nueva y renombra: mas barato y atomico que borrar 3640 filas
        # con una subconsulta correlacionada, y deja la original hasta el commit.
        cur.execute(f"""
            create temp table ref_dedup as
            select min(id) as id, {k},
                   count(*)::int as veces,
                   (array_agg(contexto order by length(coalesce(contexto,'')) desc))[1] as contexto,
                   max(confianza) as confianza,
                   (array_agg(metodo_extraccion order by id))[1] as metodo_extraccion
            from referencias group by {k}""")
        cur.execute("delete from referencias where id not in (select id from ref_dedup)")
        cur.execute("""update referencias r set veces = d.veces, contexto = d.contexto
                       from ref_dedup d where r.id = d.id""")
        cn.commit()
        cur.execute("select count(*) n from referencias")
        print(f"\nAPLICADO: {antes} -> {cur.fetchone()['n']} filas, frecuencia en `veces`")


if __name__ == "__main__":
    main(aplicar="--aplicar" in sys.argv)
