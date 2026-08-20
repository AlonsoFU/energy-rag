"""B4.2 — diff incremental: detecta que cambio en el corpus y a QUE afecta.

Dos modos, separados a proposito:

  --snapshot   congela el estado actual de la DB en `norma_snapshot` (baseline).
               Es lo primero que hay que correr; sin baseline no hay con que comparar.
  (default)    compara el estado ACTUAL de `normas` contra el snapshot y escribe
               los cambios en `norma_evento`. No toca la red.

El re-scrape desde BCN es un paso APARTE (`scripts/rescrape_partial.py` /
`src/crawlers/norm_detail_crawler.py`), a proposito: BCN devuelve 429 por cuota, asi que
bajar datos y diffear no pueden estar acoplados — si el scrape muere a medias, el diff de lo
ya bajado igual tiene que poder correr.

Flujo completo del monitor:
    1. monitor_diff --snapshot        (baseline)
    2. rescrape (crawler, con throttle)
    3. monitor_diff                   (detecta y registra)
    4. monitor_report                 (notifica lo pendiente)

LO QUE HACE UTIL AL MONITOR es `impacto`: por cada norma que cambia, busca que articulos del
corpus la CITAN (`referencias.tipo_relacion='remite'`, poblado por B3.4). La diferencia entre
"cambio la ley 21719" y "cambio la ley 21719, que citan 85 articulos tuyos" es todo el valor.

  PYTHONPATH=. venv/bin/python -m scripts.monitor_diff [--snapshot]
"""
import json
import sys

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.pipelines.texto_hash import hash_estable


def _estado_actual(cur):
    cur.execute("""
        SELECT n.id_norma,
               n.texto_completo                       AS _texto,
               n.metadata->>'estado'                  AS estado,
               coalesce(jsonb_array_length(
                   CASE WHEN jsonb_typeof(n.metadata->'versiones')='array'
                        THEN n.metadata->'versiones' ELSE '[]'::jsonb END), 0) AS n_versiones,
               (SELECT count(*) FROM articulos a WHERE a.id_norma = n.id_norma) AS n_articulos
        FROM normas n
    """)
    out = {}
    for r in cur.fetchall():
        # hash ESTABLE, no el content_hash crudo: ese cambia con cualquier espacio o pedazo
        # de interfaz de BCN. Medido: 13 de 25 normas acusaban "texto_modificado" y TODAS
        # eran cosmeticas (LEY 20365 daba similitud 1.0000).
        r["content_hash"] = hash_estable(r.pop("_texto") or "")
        out[r["id_norma"]] = r
    return out


def _vinculaciones(cur):
    cur.execute("SELECT origen, destino, tipo_relacion FROM norma_vinculacion")
    out = {}
    for r in cur.fetchall():
        out.setdefault(r["origen"], set()).add((r["destino"], r["tipo_relacion"]))
    return out


def _impacto(cur, id_norma):
    """Articulos del corpus que CITAN esta norma. Lo que vuelve accionable al evento."""
    cur.execute("""
        SELECT a.id_norma AS norma, a.numero AS articulo
        FROM referencias r JOIN articulos a ON a.id = r.origen_articulo_id
        WHERE r.tipo_relacion = 'remite' AND r.destino_norma_id = %s
        GROUP BY 1, 2 ORDER BY 1, 2
    """, (id_norma,))
    cits = [f"{r['norma']}/{r['articulo']}" for r in cur.fetchall()]
    return {"citada_por": cits, "n_citas": len(cits)}


def snapshot():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        act, vin = _estado_actual(cur), _vinculaciones(cur)
        cur.execute("TRUNCATE norma_snapshot")
        cur.executemany(
            """INSERT INTO norma_snapshot
               (id_norma, content_hash, estado, n_versiones, n_articulos, vinculaciones)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            [(k, v["content_hash"], v["estado"], v["n_versiones"], v["n_articulos"],
              json.dumps(sorted(list(vin.get(k, set())))))
             for k, v in act.items()])
        c.commit()
    print(f"snapshot tomado: {len(act)} normas")


def diff():
    eventos = []
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        act, vin = _estado_actual(cur), _vinculaciones(cur)
        cur.execute("SELECT * FROM norma_snapshot")
        prev = {r["id_norma"]: r for r in cur.fetchall()}
        if not prev:
            print("ERROR: no hay snapshot. Corre primero: --snapshot")
            return 1

        for nid, a in act.items():
            p = prev.get(nid)
            if p is None:
                eventos.append((nid, "norma_nueva", None, nid, {"n_articulos": a["n_articulos"]}))
                continue
            if a["content_hash"] and p["content_hash"] and a["content_hash"] != p["content_hash"]:
                eventos.append((nid, "texto_modificado", p["content_hash"], a["content_hash"],
                                {"n_articulos_antes": p["n_articulos"],
                                 "n_articulos_ahora": a["n_articulos"]}))
            if (a["n_versiones"] or 0) > (p["n_versiones"] or 0):
                eventos.append((nid, "version_nueva", str(p["n_versiones"]),
                                str(a["n_versiones"]), {}))
            if (a["estado"] or "") != (p["estado"] or ""):
                eventos.append((nid, "estado_cambiado", p["estado"], a["estado"], {}))
            nuevas = vin.get(nid, set()) - {tuple(x) for x in (p["vinculaciones"] or [])}
            for dest, tipo in sorted(nuevas):
                eventos.append((nid, "vinculacion_nueva", None, f"{tipo}:{dest}",
                                {"destino": dest, "tipo": tipo}))

        filas = []
        for nid, tipo, antes, despues, det in eventos:
            filas.append((nid, tipo, antes, despues, json.dumps(det),
                          json.dumps(_impacto(cur, nid))))
        if filas:
            cur.executemany(
                """INSERT INTO norma_evento
                   (id_norma, tipo_evento, valor_antes, valor_despues, detalle, impacto)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT DO NOTHING""", filas)
            c.commit()

    print(f"cambios detectados: {len(eventos)}")
    for nid, tipo, antes, despues, _ in eventos[:20]:
        print(f"  {tipo:20} {nid:>9}  {str(antes)[:16]} -> {str(despues)[:24]}")
    if not eventos:
        print("  (sin cambios respecto al snapshot)")
    return 0


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
    else:
        raise SystemExit(diff())
