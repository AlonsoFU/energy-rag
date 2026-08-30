"""E1/B3.7 — bajar las normas candidatas que el corpus NO tiene.

Entrada: `docs/descubrimiento-pendiente.md` (fuente 1: citadas desde el dominio y ausentes).
El orden ya viene por veces citada desde normas NO marcadas `fuera_de_dominio`.

Resolucion tipo+numero -> idNorma: BCN no expone un endpoint directo, pero el buscador
`consulta/listaresultadosimple?cadena=<numero>` devuelve enlaces con `idNorma=`. Verificado a
mano con LEY 20936 -> idNorma 1092695 (240.608 chars, "ESTABLECE UN NUEVO SISTEMA DE
TRANSMISION ELECTRICA Y CREA UN ORGANISMO COORDINADOR").

FILTRO DE DOMINIO: cada norma bajada se mide contra las funciones de la subgerencia igual que
el resto del corpus (`marcar_fuera_dominio`), por ARTICULADO y no por titulo. Si no pasa el
corte se guarda igual pero marcada — no se descarta a mano.

  PYTHONPATH=. venv/bin/python -m scripts.bajar_candidatas [--limit N] [--delay S] [--dry]
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

DOC = Path("docs/descubrimiento-pendiente.md")
ESTADO = Path("data/eval/results/candidatas_bajadas.json")
BUSCADOR = "https://www.bcn.cl/leychile/consulta/listaresultadosimple?cadena={}"
# Tolera una primera columna numerica opcional: el reporte de frontera ahora abre con `dom`
# (puntaje de dominio del contexto) y antes empezaba directo por el tipo.
FILA = re.compile(r"^\|\s*(?:[\d.]+\s*\|\s*)?(LEY|DECRETO|DFL|DL|RESOLUCI[OÓ]N)\s*\|"
                  r"\s*([\d]+)\s*\|\s*\**(\d+)\**\s*\|")


def candidatas(limit=0, doc=None):
    """Lee la tabla de candidatas de un reporte de descubrimiento.

    `doc` permite apuntar a otra fuente con la misma forma de tabla — hoy tambien
    `docs/normativa-usada-en-discrepancias.md`, que es descubrimiento por USO: normas que el
    sector cita en sus discrepancias ante el Panel y el corpus no tiene.
    """
    out, visto = [], set()
    for ln in Path(doc or DOC).read_text().splitlines():
        m = FILA.match(ln.strip())
        if not m:
            continue
        tipo, num, cit = m.group(1).upper(), m.group(2), int(m.group(3))
        if (tipo, num) in visto:
            continue
        visto.add((tipo, num))
        out.append({"tipo": tipo, "numero": num, "citas": cit})
        if limit and len(out) >= limit:
            break
    return out


AVISO_DOMINIO = 0.30      # mismo corte que `marcar_fuera_dominio.CORTE`
_REF_DOMINIO = None


def dominio_sim(texto):
    """Parecido del ARTICULADO bajado con las funciones de la subgerencia. None si no se puede."""
    global _REF_DOMINIO
    try:
        from scripts.frontera_mercados import DOMINIO
        from scripts.marcar_fuera_dominio import _v
        if _REF_DOMINIO is None:
            _REF_DOMINIO = _v(re.sub(r"\s+", " ", DOMINIO).strip())
        a = _REF_DOMINIO
        b = _v(re.sub(r"\s+", " ", (texto or ""))[:4000])
        if not a or not b:
            return None
        return sum(x * y for x, y in zip(a, b))
    except Exception:
        return None


def _guardar(d, v):
    out = Path(f"data/normas_completas/nuevas/{v['id_norma']}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "id_norma": v["id_norma"], "tipo": d.tipo, "numero": d.numero,
        "titulo": d.titulo, "fecha_publicacion": d.fecha_publicacion,
        "organismo": d.organismo, "estado": d.estado, "url": d.url,
        "texto_completo": d.texto_completo, "content_hash": d.content_hash,
        "vinculaciones": d.vinculaciones, "versiones": d.versiones,
    }, ensure_ascii=False))
    return out


def identidad_ok(tipo_pedido, num_pedido, d):
    """La norma bajada, ¿es la que se pidio?

    El buscador de BCN resuelve por NUMERO y nada mas: `DECRETO 42` devolvio `ACUERDO 42`, y
    8 de 24 descargas de una tanda anterior eran otra norma. Se compara lo que declara la
    propia norma bajada contra lo que se pidio.

    Se exige tipo Y numero. El tipo se compara contra el titulo ademas del campo `tipo`
    porque BCN a veces deja `tipo` vacio y solo lo escribe en el encabezado del titulo.
    """
    n_ped = re.sub(r"[^\d]", "", str(num_pedido or "")).lstrip("0")
    n_bajo = re.sub(r"[^\d]", "", str(getattr(d, "numero", "") or "")).lstrip("0")
    if n_bajo and n_ped and n_bajo != n_ped:
        return False
    t_ped = str(tipo_pedido or "").upper().strip()
    t_bajo = str(getattr(d, "tipo", "") or "").upper().strip()
    titulo = str(getattr(d, "titulo", "") or "").upper()
    if not t_bajo:
        t_bajo = titulo.split()[0] if titulo.split() else ""
    if not t_bajo:
        return True                     # sin dato de tipo no se puede desmentir
    # DECRETO SUPREMO / DECRETO EXENTO cuentan como DECRETO; ACUERDO no.
    return t_bajo.startswith(t_ped) or t_ped.startswith(t_bajo)


def ya_en_corpus():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero FROM normas")
        r = cur.fetchall()
    return ({x["id_norma"] for x in r},
            {(str(x["tipo"]).upper(), str(x["numero"]).replace(".", "").lstrip("0")) for x in r})


async def resolver(pg, numero):
    """tipo+numero -> idNorma via el buscador de BCN. None si no resuelve."""
    await pg.goto(BUSCADOR.format(numero), wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(6)   # el buscador renderiza por JS; 2.5s dejaba resultados vacios
    ids = await pg.evaluate("""() => [...document.querySelectorAll('a[href*="idNorma"]')]
        .map(a => a.href.match(/idNorma=(\\d+)/)?.[1]).filter(Boolean)""")
    return ids[0] if ids else None


async def main(limit=0, delay=20, dry=False, fuente=None):
    from src.crawlers.norm_detail_crawler import NormDetailCrawler

    ids_corpus, pares_corpus = ya_en_corpus()
    cands = [c for c in candidatas(doc=fuente)
             if (c["tipo"], c["numero"].lstrip("0")) not in pares_corpus]
    if limit:
        cands = cands[:limit]
    hechas = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    print(f"candidatas a bajar: {len(cands)}  (ya procesadas: {len(hechas)})", flush=True)

    async with Stealth().use_async(async_playwright()) as p:
        b = await p.chromium.launch(headless=True)
        pg = await (await b.new_context()).new_page()
        for i, c in enumerate(cands, 1):
            k = f"{c['tipo']}-{c['numero']}"
            if k in hechas:
                continue
            nid = await resolver(pg, c["numero"])
            print(f"[{i}/{len(cands)}] {c['tipo']} {c['numero']} ({c['citas']} citas) "
                  f"-> idNorma {nid}", flush=True)
            if not nid:
                hechas[k] = {"estado": "no_resuelto"}
            elif nid in ids_corpus:
                hechas[k] = {"estado": "ya_estaba", "id_norma": nid}
                print("     ya estaba en el corpus con otro tipo/numero", flush=True)
            else:
                hechas[k] = {"estado": "resuelto", "id_norma": nid, "citas": c["citas"]}
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps(hechas, ensure_ascii=False, indent=1))
            await asyncio.sleep(delay)
        await b.close()

    listos = [(k, v) for k, v in hechas.items() if v.get("estado") == "resuelto"]
    print(f"\n=== resueltos {len(listos)} idNorma ===", flush=True)
    if dry:
        print("(DRY — no se descarga el texto)", flush=True)
        return

    async with NormDetailCrawler() as cr:
        for j, (k, v) in enumerate(listos, 1):
            if v.get("descargado"):
                continue
            d = await cr.fetch_norm(v["id_norma"])
            if not d or len(d.texto_completo) < 500:
                v["descargado"] = False
                print(f"  [{j}/{len(listos)}] {k}: FALLO o vacio", flush=True)
            elif (sim := dominio_sim(d.texto_completo)) is not None and sim < AVISO_DOMINIO:
                # Tipo y numero pueden coincidir y aun asi ser otra norma: el DECRETO 88 que
                # devolvio BCN era un decreto exento del Ministerio de EDUCACION de 1994, con
                # numero y tipo correctos. La materia es la unica señal que lo separa. Se
                # puntua por ARTICULADO contra las funciones de la subgerencia, igual que
                # `marcar_fuera_dominio` -- por titulo no sirve, la formula burocratica del
                # encabezado legal chileno es identica entre materias.
                # Se GUARDA igual pero se avisa: la frontera es una decision aparte, y
                # descartar en silencio esconderia un acierto legitimo mal puntuado.
                v["descargado"] = True
                v["dominio_sim"] = round(sim, 3)
                out = _guardar(d, v)
                print(f"  [{j}/{len(listos)}] {k}: GUARDADO pero DUDOSO "
                      f"(dominio {sim:.3f} < {AVISO_DOMINIO}) -> {out.name}", flush=True)
                print(f"        titulo: {(d.titulo or '')[:80]}", flush=True)
            elif not identidad_ok(v["tipo"], v["numero"], d):
                # El buscador de BCN resuelve SOLO por numero, asi que devuelve cualquier
                # norma que lleve ese numero. Pedir "DECRETO 44" (Reglamento del Panel de
                # Expertos) trajo el ACUERDO 44/2001 del Ministerio de Educacion sobre el
                # Instituto Profesional Zipter, y "DECRETO 88" trajo un decreto exento de
                # Educacion de 1994. Sin esta guarda se guardaban igual.
                v["descargado"] = False
                v["rechazo"] = f"identidad: pedido {v['tipo']} {v['numero']}, vino {d.tipo} {d.numero}"
                print(f"  [{j}/{len(listos)}] {k}: RECHAZADO -- {v['rechazo']}", flush=True)
                print(f"        titulo: {(d.titulo or '')[:80]}", flush=True)
            else:
                out = Path(f"data/normas_completas/nuevas/{v['id_norma']}.json")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps({
                    "id_norma": v["id_norma"], "tipo": d.tipo, "numero": d.numero,
                    "titulo": d.titulo, "fecha_publicacion": d.fecha_publicacion,
                    "organismo": d.organismo, "estado": d.estado, "url": d.url,
                    "texto_completo": d.texto_completo, "content_hash": d.content_hash,
                    "vinculaciones": d.vinculaciones, "versiones": d.versiones,
                }, ensure_ascii=False))
                v["descargado"] = True
                v["chars"] = len(d.texto_completo)
                print(f"  [{j}/{len(listos)}] {k}: {len(d.texto_completo)} chars -> {out.name}",
                      flush=True)
            ESTADO.write_text(json.dumps(hechas, ensure_ascii=False, indent=1))
            await asyncio.sleep(delay)

    ok = sum(1 for _k, v in hechas.items() if v.get("descargado"))
    print(f"\n=== descargadas {ok} normas a data/normas_completas/nuevas/ ===", flush=True)
    print("Siguiente: ingesta + embeddings + marcado de dominio", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=int, default=20)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--fuente", default=None,
                    help="reporte de donde leer las candidatas (default: descubrimiento-pendiente)")
    a = ap.parse_args()
    asyncio.run(main(a.limit, a.delay, a.dry, a.fuente))
