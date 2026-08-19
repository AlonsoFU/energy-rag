"""B3.3 — re-bajar de BCN las normas que fueron MODIFICADAS, y detectar si cambiaron.

Riesgo real medido en E3: el grafo dice que 25 normas del corpus fueron modificadas por otras,
pero el texto guardado puede ser la version ANTERIOR a esa modificacion. Si es asi, el sistema
esta citando texto derogado o superado — el peor error posible en un sistema legal.

Este script no reingesta nada por su cuenta. Baja, compara el `content_hash` y **registra el
resultado como eventos** (`norma_evento`), que es el mecanismo del monitor B4. Asi el
diagnostico queda auditable y la reingesta es una decision explicita despues.

Throttle obligatorio: BCN devuelve 429 por cuota. Default 20 s entre normas, resumible
(saltea las que ya reviso en esta corrida).

  PYTHONPATH=. venv/bin/python -m scripts.rescrape_modificadas [--limit N] [--delay S]
"""
import argparse
import asyncio
import json
import re
from datetime import date
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.crawlers.norm_detail_crawler import NormDetailCrawler

ESTADO = Path("data/eval/results/rescrape_modificadas.json")


def _incompleto(texto, largo_guardado, tolerancia=0.9):
    """True si el texto bajado no es confiable como base de comparacion.

    Dos senales: quedaron placeholders 'Loading' del render perezoso de BCN, o el texto
    encogio mas alla de la tolerancia. Una norma REAL puede acortarse al derogarse
    articulos, por eso no basta el largo solo — pero un encogimiento fuerte SIN que se
    haya bajado bien la pagina es casi siempre un scrape truncado.
    """
    texto = texto or ""
    if re.search(r"\bLoading\b", texto):
        return True
    if largo_guardado and len(texto) < largo_guardado * tolerancia:
        return True
    return False


def objetivo():
    """Normas del corpus que alguna otra norma MODIFICA."""
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT DISTINCT v.destino AS id_norma, n.tipo, n.numero, n.titulo,
                   n.metadata->>'content_hash' AS hash_guardado,
                   length(n.texto_completo)   AS largo_guardado
            FROM norma_vinculacion v JOIN normas n ON n.id_norma = v.destino
            WHERE v.tipo_relacion ILIKE '%%modific%%'
            ORDER BY 1
        """)
        return cur.fetchall()


def registrar(id_norma, tipo_evento, antes, despues, detalle, ):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT a.id_norma AS norma, a.numero AS articulo
            FROM referencias r JOIN articulos a ON a.id = r.origen_articulo_id
            WHERE r.tipo_relacion='remite' AND r.destino_norma_id=%s
            GROUP BY 1,2""", (id_norma,))
        cits = [f"{r['norma']}/{r['articulo']}" for r in cur.fetchall()]
        cur.execute("""
            INSERT INTO norma_evento
              (id_norma, tipo_evento, fecha_evento, valor_antes, valor_despues, detalle, impacto)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (id_norma, tipo_evento, date.today(), antes, despues,
             json.dumps(detalle), json.dumps({"citada_por": cits, "n_citas": len(cits)})))
        c.commit()


async def main(limit=0, delay=20):
    objs = objetivo()
    if limit:
        objs = objs[:limit]
    hechas = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    print(f"normas modificadas a revisar: {len(objs)}  (ya revisadas: {len(hechas)})", flush=True)

    cambiadas = iguales = fallo = 0
    async with NormDetailCrawler() as cr:
        for i, o in enumerate(objs, 1):
            nid = o["id_norma"]
            if nid in hechas:
                continue
            print(f"[{i}/{len(objs)}] {nid} {o['tipo']} {o['numero']}", flush=True)
            try:
                d = await cr.fetch_norm(nid)
            except Exception as ex:
                d = None
                print(f"   ERROR {type(ex).__name__}: {ex}", flush=True)
            if not d:
                fallo += 1
                hechas[nid] = {"estado": "fallo"}
            elif _incompleto(d.texto_completo, o["largo_guardado"]):
                # NO registrar como cambio: un scrape truncado se ve identico a una
                # modificacion real (mismo sintoma: cambia el content_hash). Medido en
                # LEY 20365 -- 30.087 chars guardados vs 23.391 bajados, cortado en 'Loading'.
                fallo += 1
                hechas[nid] = {"estado": "scrape_incompleto",
                               "largo_guardado": o["largo_guardado"],
                               "largo_bajado": len(d.texto_completo or "")}
                print(f"   ✗ SCRAPE INCOMPLETO ({o['largo_guardado']} -> "
                      f"{len(d.texto_completo or '')} chars) -- NO se registra evento", flush=True)
            elif d.content_hash != (o["hash_guardado"] or ""):
                cambiadas += 1
                hechas[nid] = {"estado": "cambio", "antes": o["hash_guardado"],
                               "despues": d.content_hash}
                registrar(nid, "texto_modificado", o["hash_guardado"], d.content_hash,
                          {"origen": "rescrape_modificadas", "estado_bcn": d.estado,
                           "n_versiones": len(d.versiones or [])})
                print(f"   ⚠️ CAMBIO  {o['hash_guardado']} -> {d.content_hash}", flush=True)
            else:
                iguales += 1
                hechas[nid] = {"estado": "igual", "hash": d.content_hash}
                print("   ok (sin cambios)", flush=True)
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps(hechas, ensure_ascii=False, indent=1))
            await asyncio.sleep(delay)

    print(f"\n=== cambiadas {cambiadas} · iguales {iguales} · fallo {fallo} ===", flush=True)
    print("los cambios quedaron en `norma_evento`; ver con scripts.monitor_report", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=int, default=20)
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.delay))
