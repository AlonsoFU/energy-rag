"""Artículos que aparecen en DOS normas: una ley modificatoria y el cuerpo que modifica.

El problema, encontrado en LEY 20936. Esa ley son 41 numerales que modifican la LGSE, y el
ingestor guardó como suyos los artículos que la ley **inserta en la LGSE**: 55 de sus 63
artículos son `72°`-`122°` y `212°`, que pertenecen al DFL 4. Los 55 existen también en DFL 4,
con mejor numeración (`72º-13` contra un `72º` al que el parser le comió el `-13`).

Por qué importa: el sistema responde `[LEY 20936 art 92°]` cuando la cita correcta es
`[DFL 4 art 92°]`. En materia legal eso es una **cita falsa** — la ley modificatoria introdujo
ese artículo, pero el artículo vigente pertenece al cuerpo que lo contiene.

**Se detecta por CONTENIDO, no por una lista de normas.** Dos artículos con el mismo número y
texto casi idéntico en dos normas distintas son el mismo artículo contado dos veces. Se
conserva en la norma que tiene MÁS artículos de esa numeración —el cuerpo principal, no la
modificatoria— y se marca el duplicado en la otra. Ningún nombre de norma va escrito acá.

MARCA, no borra: `metadata.duplicado_de` es reversible; un DELETE no.

  PYTHONPATH=. venv/bin/python -m scripts.detectar_articulos_duplicados [--aplicar]
"""
import argparse
import collections
import difflib
import re

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

UMBRAL = 0.90          # similitud de texto para considerarlos el MISMO articulo


def norm_num(n):
    """'72º-13' y '72°-13' son el mismo numero; '72°' y '72-13' NO lo son."""
    s = re.sub(r"[°º\s]+", "", (n or "").lower())
    return re.sub(r"[^\w\-]", "", s)


def main(aplicar=False):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT a.id, a.id_norma, a.numero, coalesce(a.texto,'') texto,
                              n.tipo, n.numero AS nnum
                       FROM articulos a JOIN normas n ON n.id_norma = a.id_norma
                       WHERE a.texto IS NOT NULL AND length(a.texto) > 80
                         AND n.metadata->>'fuera_de_dominio' IS DISTINCT FROM 'true'""")
        arts = cur.fetchall()

    por_num = collections.defaultdict(list)
    for a in arts:
        por_num[norm_num(a["numero"])].append(a)
    # cuantos articulos aporta cada norma: el cuerpo principal tiene muchos mas que la
    # modificatoria, y esa es la senal que decide cual se conserva.
    tam = collections.Counter(a["id_norma"] for a in arts)

    dups, ambiguos = [], []
    for num, grupo in por_num.items():
        if len(grupo) < 2:
            continue
        for i in range(len(grupo)):
            for j in range(i + 1, len(grupo)):
                a, b = grupo[i], grupo[j]
                if a["id_norma"] == b["id_norma"]:
                    continue
                sim = difflib.SequenceMatcher(None, a["texto"][:3000], b["texto"][:3000]).ratio()
                if sim < UMBRAL:
                    continue
                ta, tb = tam[a["id_norma"]], tam[b["id_norma"]]
                if ta == tb:
                    # EMPATE: no hay cuerpo principal que distinguir. Con >= se marcaban
                    # LOS DOS lados del par (visto en DECRETO 7 <-> DECRETO 8, 5 articulos
                    # cada uno) y el articulo desaparecia entero. Ante empate no se adivina.
                    ambiguos.append({"a": a, "b": b, "sim": round(sim, 3)})
                    continue
                queda, sobra = (a, b) if ta > tb else (b, a)
                dups.append({"sobra": sobra, "queda": queda, "sim": round(sim, 3)})

    print(f"articulos comparados      : {len(arts)}")
    print(f"numeros presentes en >1 norma: {sum(1 for g in por_num.values() if len(g) > 1)}")
    print(f"duplicados (sim >= {UMBRAL}) : {len(dups)}")
    print(f"ambiguos (empate, NO se marcan): {len(ambiguos)}")
    for x in ambiguos[:6]:
        print(f"     {x['a']['tipo']} {x['a']['nnum']} art {x['a']['numero']} <-> "
              f"{x['b']['tipo']} {x['b']['nnum']} art {x['b']['numero']}  sim={x['sim']}")
    por_norma = collections.Counter(
        f"{d['sobra']['tipo']} {d['sobra']['nnum']} -> {d['queda']['tipo']} {d['queda']['nnum']}"
        for d in dups)
    for k, n in por_norma.most_common(12):
        print(f"  {n:4}  {k}")

    if aplicar:
        with with_connection() as c, c.cursor() as cur:
            cur.executemany(
                """UPDATE articulos SET metadata = coalesce(metadata,'{}'::jsonb)
                   || jsonb_build_object('duplicado_de', %s::text, 'duplicado_sim', %s::text)
                   WHERE id = %s""",
                [(d["queda"]["id_norma"], str(d["sim"]), d["sobra"]["id"]) for d in dups])
            c.commit()
        print(f"\nMARCADOS {len(dups)} articulos con metadata.duplicado_de (reversible)")
    else:
        print("\n(simulacion — usar --aplicar para marcar)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true")
    main(ap.parse_args().aplicar)
