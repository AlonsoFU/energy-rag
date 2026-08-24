"""B3.3 — re-bajar de BCN las normas que fueron MODIFICADAS, y detectar si cambiaron.

Riesgo real medido en E3: el grafo dice que 25 normas del corpus fueron modificadas por otras,
pero el texto guardado puede ser la version ANTERIOR a esa modificacion. Si es asi, el sistema
esta citando texto derogado o superado — el peor error posible en un sistema legal.

Este script no reingesta nada por su cuenta. Baja, compara el **hash ESTABLE** del texto
(`src/pipelines/texto_hash.py` — normaliza espacio/tildes/chrome de BCN antes de hashear, porque
el `content_hash` crudo cambia con cualquier espacio: 13 de 25 daban "cambio" y TODAS eran
cosmeticas) y **registra el
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
from src.pipelines.texto_hash import cambio_real, hash_estable, similitud

ESTADO = Path("data/eval/results/rescrape_modificadas.json")


def _incompleto(texto, largo_guardado, tolerancia=0.9):
    """True si el texto bajado no es confiable como base de comparacion.

    Dos senales: quedaron placeholders 'Loading' del render perezoso de BCN, o el texto
    encogio mas alla de la tolerancia. Una norma REAL puede acortarse al derogarse
    articulos, por eso no basta el largo solo — pero un encogimiento fuerte SIN que se
    haya bajado bien la pagina es casi siempre un scrape truncado.
    """
    texto = texto or ""
    if largo_guardado and len(texto) >= largo_guardado:
        # tan largo o mas que lo guardado => bajo completo. La palabra "Loading" puede
        # aparecer en el chrome de la pagina (footer/UI) sin que falte articulado: sin este
        # corte se rechazaban textos INTEGROS (medido: 3 de 25 con el largo exacto igual).
        return False
    if re.search(r"\bLoading\b", texto):
        return True
    if largo_guardado and len(texto) < largo_guardado * tolerancia:
        return True
    return False


COLS = """n.id_norma, n.tipo, n.numero, n.titulo,
          n.metadata->>'content_hash' AS hash_guardado,
          n.texto_completo           AS texto_guardado,
          length(n.texto_completo)   AS largo_guardado"""


def objetivo(alcance="dominio"):
    """Qué normas se re-bajan.

    `modificadas` — las que el grafo de BCN marca como modificadas por otra norma. Era el
    alcance original y sirve para un diagnóstico puntual, PERO cubre 16 de las 70 normas en
    dominio (23 %). Como monitor periódico da falsa seguridad: las otras 54 pueden cambiar
    sin que nadie se entere, porque `norma_vinculacion` viene incompleta desde BCN (204 filas
    para 111 normas) y NO es un registro confiable de qué se modificó.

    `dominio` (default) — las 70 normas del corpus dentro de la frontera de mercados. Es lo
    que un monitor tiene que mirar: se re-baja todo y **el texto decide**, no el metadato.
    A 20 s de throttle son ~40 min por pasada, viable semanalmente.
    """
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        if alcance == "modificadas":
            cur.execute(f"""
                SELECT DISTINCT {COLS}
                FROM norma_vinculacion v JOIN normas n ON n.id_norma = v.destino
                WHERE v.tipo_relacion ILIKE '%%modific%%'
                ORDER BY 1
            """)
        else:
            cur.execute(f"""
                SELECT {COLS} FROM normas n
                WHERE n.metadata->>'fuera_de_dominio' IS DISTINCT FROM 'true'
                  AND n.texto_completo IS NOT NULL
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


def _vencida(reg, frescura):
    """True si hay que volver a revisar esta norma.

    BUG que esto arregla: `hechas` no caducaba nunca. La primera pasada dejaba las 25 normas
    marcadas y **la segunda encontraba 0 pendientes** — un monitor semanal que a partir de la
    semana 2 no mira nada y sigue informando "sin cambios". El estado servia para RESUMIR una
    corrida cortada, no para correr periodicamente.

    `frescura=0` fuerza revisar todo (util para una corrida manual completa).
    """
    if not isinstance(reg, dict) or frescura <= 0:
        return True
    v = reg.get("revisado_en")
    if not v:
        return True          # estado del formato viejo: sin fecha, se revisa
    try:
        return (date.today() - date.fromisoformat(v)).days >= frescura
    except ValueError:
        return True


async def main(limit=0, delay=20, alcance="dominio", frescura=6):
    objs = objetivo(alcance)
    if limit:
        objs = objs[:limit]
    hechas = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    print(f"alcance={alcance}  normas a revisar: {len(objs)}  "
          f"(con registro previo: {len(hechas)}, frescura {frescura} d)", flush=True)

    cambiadas = iguales = fallo = 0
    # RECICLAR el browser cada REINICIO normas: en la primera corrida completa, normas que
    # bajaban integras de a una (DFL 1: 329.285 chars) salian truncadas al 8% dentro de una
    # tanda larga. El contexto de Playwright se degrada / BCN empieza a servir a medias.
    REINICIO = 5
    pendientes = [o for o in objs if _vencida(hechas.get(o["id_norma"]), frescura)]
    print(f"pendientes en esta pasada: {len(pendientes)}", flush=True)
    for bloque in range(0, len(pendientes), REINICIO):
      async with NormDetailCrawler() as cr:
        for i, o in enumerate(pendientes[bloque:bloque + REINICIO], bloque + 1):
            nid = o["id_norma"]
            print(f"[{i}/{len(pendientes)}] {nid} {o['tipo']} {o['numero']}", flush=True)
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
            elif cambio_real(o["texto_guardado"] or "", d.texto_completo):
                # `cambio_real` = hash estable distinto Y similitud < 0.995. El hash SOLO no
                # alcanza: se cazo aca mismo un falso positivo en LEY 20365 -- mismo largo
                # exacto (30.087 chars) y similitud 0.9997, marcado como "CAMBIO REAL". Es la
                # misma trampa de los 13 eventos cosmeticos, que se habia arreglado en
                # `monitor_diff` y NO aca. La similitud queda guardada para poder auditarlo.
                cambiadas += 1
                he_viejo = hash_estable(o["texto_guardado"] or "")
                he_nuevo = hash_estable(d.texto_completo)
                sim = round(similitud(o["texto_guardado"] or "", d.texto_completo), 4)
                hechas[nid] = {"estado": "cambio", "antes": he_viejo, "despues": he_nuevo,
                               "similitud": sim}
                registrar(nid, "texto_modificado", he_viejo, he_nuevo,
                          {"origen": "rescrape_modificadas", "estado_bcn": d.estado,
                           "similitud": sim, "n_versiones": len(d.versiones or [])})
                print(f"   ⚠️ CAMBIO REAL  {he_viejo} -> {he_nuevo}  (sim {sim})", flush=True)
            elif hash_estable(d.texto_completo) != hash_estable(o["texto_guardado"] or ""):
                # hash distinto pero similitud alta: cambio COSMETICO de BCN. Se anota para
                # que la proxima pasada no lo vuelva a mirar, y no se registra evento.
                iguales += 1
                hechas[nid] = {"estado": "cosmetico",
                               "similitud": round(similitud(o["texto_guardado"] or "",
                                                            d.texto_completo), 4)}
                print(f"   ~ cosmetico (sim {hechas[nid]['similitud']}) -- sin evento", flush=True)
            else:
                iguales += 1
                hechas[nid] = {"estado": "igual", "hash": hash_estable(d.texto_completo)}
                print("   ok (sin cambios)", flush=True)
            hechas[nid]["revisado_en"] = date.today().isoformat()
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps(hechas, ensure_ascii=False, indent=1))
            await asyncio.sleep(delay)

    print(f"\n=== cambiadas {cambiadas} · iguales {iguales} · fallo {fallo} ===", flush=True)
    print("los cambios quedaron en `norma_evento`; ver con scripts.monitor_report", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=int, default=20)
    ap.add_argument("--alcance", choices=["dominio", "modificadas"], default="dominio",
                    help="dominio = las 70 del corpus (monitor); modificadas = las 16 del grafo")
    ap.add_argument("--frescura", type=int, default=6,
                    help="dias antes de volver a revisar una norma (0 = revisar todas)")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.delay, a.alcance, a.frescura))
