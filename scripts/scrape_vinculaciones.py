"""D1/G7: scrapea BCN y construye el grafo norma→norma (modifica / deroga).

Corrige un error de diagnóstico previo: con `curl`, BCN devuelve 429 en `obtxml` y una cáscara
JS en el HTML, y se dio D1 por BLOQUEADO. Falso: el corpus original se bajó con
`src/crawlers/norm_detail_crawler.py` (Playwright + stealth), que SÍ renderiza y ya trae
`_extract_vinculaciones`. Verificado en 258171:
    {'modifica_a': [], 'modificada_por': [{'id_norma':'1092695','numero':'20936',
     'articulo':'Art. 1 N° 1 a)','fecha_do':'20.07.2016', ...}]}

⚠️ `estado` viene DESCONOCIDO incluso desde BCN → la vigencia se DERIVA de las vinculaciones
(`derogada_por` no vacío ⇒ derogada), no se lee de un campo.

Escribe en `norma_norma(origen, destino, tipo_relacion)` y en `normas.metadata.estado`.
Resumible: saltea las normas ya scrapeadas (guarda cada 5). Lento a propósito (BCN rate-limita).

Uso:  PYTHONPATH=. venv/bin/python -m scripts.scrape_vinculaciones          (dry, 3 normas)
      WRITE=1 LIMIT=0 PYTHONPATH=. venv/bin/python -m scripts.scrape_vinculaciones
"""
import asyncio, json, os
from pathlib import Path
from src.storage.connection import with_connection
from src.crawlers.norm_detail_crawler import NormDetailCrawler

WRITE = os.environ.get("WRITE") == "1"
LIMIT = int(os.environ.get("LIMIT", "3"))
CACHE = Path("data/eval/results/bcn_vinculaciones.json")


async def main():
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id_norma FROM normas ORDER BY id_norma")
        ids = [str(r[0]) for r in cur.fetchall()]
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    falta = [i for i in ids if i not in cache]
    if LIMIT:
        falta = falta[:LIMIT]
    print(f"normas: {len(ids)} | ya scrapeadas: {len(cache)} | a scrapear ahora: {len(falta)}", flush=True)

    c = NormDetailCrawler(headless=True)
    await c.start()
    try:
        for n, idn in enumerate(falta, 1):
            try:
                d = await c.fetch_norm(idn)
                if d:
                    cache[idn] = {"estado": d.estado, "tipo": d.tipo, "numero": d.numero,
                                  "vinculaciones": d.vinculaciones, "titulo": (d.titulo or "")[:120]}
                else:
                    cache[idn] = {"error": "None"}
            except Exception as ex:
                cache[idn] = {"error": type(ex).__name__}
                print(f"  ! {idn}: {type(ex).__name__}", flush=True)
            if n % 5 == 0:
                CACHE.parent.mkdir(parents=True, exist_ok=True)
                CACHE.write_text(json.dumps(cache, ensure_ascii=False, default=str))
                print(f"  {n}/{len(falta)}", flush=True)
            await asyncio.sleep(2)          # cortesia con BCN
    finally:
        await c.close()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, default=str))

    # --- resumen + derivacion de vigencia ---
    ok = [k for k, v in cache.items() if "error" not in v]
    derog, modif, aristas = [], [], []
    for idn in ok:
        v = cache[idn].get("vinculaciones") or {}
        for rel, key in (("derogada_por", "derogada_por"), ("modificada_por", "modificada_por"),
                         ("deroga_a", "deroga_a"), ("modifica_a", "modifica_a")):
            for item in (v.get(key) or []):
                dest = str(item.get("id_norma") or "")
                if not dest:
                    continue
                if key in ("derogada_por", "modificada_por"):
                    aristas.append((dest, idn, key.replace("da_por", "")))
                else:
                    aristas.append((idn, dest, key.replace("_a", "")))
        if v.get("derogada_por"):
            derog.append(idn)
        if v.get("modificada_por"):
            modif.append(idn)
    print(f"\nscrapeadas OK: {len(ok)}/{len(cache)}")
    print(f"  DEROGADAS (derivado de derogada_por): {len(derog)}  {derog[:10]}")
    print(f"  modificadas: {len(modif)}")
    print(f"  aristas norma->norma: {len(aristas)}  (unicas: {len(set(aristas))})")

    if not WRITE:
        print("\n(dry-run; WRITE=1 para persistir)")
        return
    # OJO: `norma_norma` es una VIEW (con DISTINCT) -> no se puede insertar en ella
    # ("cannot insert into view"). Las vinculaciones de BCN van a su propia TABLA.
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS norma_vinculacion (
            origen text, destino text, tipo_relacion text, fuente text DEFAULT 'bcn',
            PRIMARY KEY (origen, destino, tipo_relacion))""")
        for o, d, t in set(aristas):
            cur.execute("INSERT INTO norma_vinculacion (origen,destino,tipo_relacion) VALUES (%s,%s,%s) "
                        "ON CONFLICT DO NOTHING", (o, d, t))
        for idn in derog:
            cur.execute("UPDATE normas SET metadata = COALESCE(metadata,'{}'::jsonb) || '{\"estado\":\"DEROGADA\"}'::jsonb "
                        "WHERE id_norma = %s", (idn,))
        conn.commit()
        cur.execute("SELECT count(*) FROM norma_vinculacion"); print(f"[WRITE] norma_vinculacion: {cur.fetchone()[0]} filas")
        cur.execute("SELECT metadata->>'estado', count(*) FROM normas GROUP BY 1"); print("[WRITE] estados:", cur.fetchall())


if __name__ == "__main__":
    asyncio.run(main())
