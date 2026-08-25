"""Bajar normas por idNorma EXPLÍCITO, cuando el buscador por número falla.

`bajar_candidatas` resuelve tipo+número contra el buscador de BCN, que busca **sólo por
número** y devuelve cualquier norma que lo lleve: pedir el `DECRETO 44` (Reglamento del Panel
de Expertos, Energía 2017) trajo el `ACUERDO 44/2001` del Ministerio de **Educación**, y el
`DECRETO 88` (PMGD, Energía 2019) trajo un decreto exento de Educación de 1994.

Cuando pasa eso, el idNorma se consigue por otra vía (búsqueda por título, el sitio del
Ministerio) y se baja directo. Este script hace eso **con las mismas dos guardas** que
`bajar_candidatas`, para que resolver el id a mano no sea una puerta trasera sin control:

    identidad_ok()  tipo y número declarados por la norma bajada
    dominio_sim()   materia por ARTICULADO contra las funciones de la subgerencia

  PYTHONPATH=. venv/bin/python -m scripts.bajar_por_id 1113260:DECRETO:44 1150437:DECRETO:88
"""
import asyncio
import json
import sys

from scripts.bajar_candidatas import (AVISO_DOMINIO, ESTADO, _guardar, dominio_sim,
                                     identidad_ok)


async def main(specs):
    from src.crawlers.norm_detail_crawler import NormDetailCrawler
    async with NormDetailCrawler() as cr:
        for i, sp in enumerate(specs, 1):
            partes = sp.split(":")
            if len(partes) != 3:
                print(f"  [{i}] '{sp}': formato esperado idNorma:TIPO:NUMERO", flush=True)
                continue
            nid, tipo, num = partes
            print(f"[{i}/{len(specs)}] {tipo} {num} (idNorma {nid})", flush=True)
            try:
                d = await cr.fetch_norm(nid)
            except Exception as ex:
                print(f"    ERROR {type(ex).__name__}: {ex}", flush=True)
                continue
            if not d or len(d.texto_completo or "") < 500:
                print("    FALLO o texto vacio", flush=True)
                continue
            print(f"    titulo: {(d.titulo or '')[:78]}", flush=True)
            print(f"    chars : {len(d.texto_completo)}", flush=True)
            if not identidad_ok(tipo, num, d):
                print(f"    RECHAZADO -- identidad: vino {d.tipo} {d.numero}", flush=True)
                continue
            sim = dominio_sim(d.texto_completo)
            if sim is not None and sim < AVISO_DOMINIO:
                # se guarda igual: la frontera es una decision aparte, y descartar en silencio
                # esconderia un acierto legitimo mal puntuado.
                print(f"    DUDOSO: dominio {sim:.3f} < {AVISO_DOMINIO} -- se guarda y se avisa",
                      flush=True)
            elif sim is not None:
                print(f"    dominio {sim:.3f}  ok", flush=True)
            out = _guardar(d, {"id_norma": nid})
            # Registrar QUE se pidio, en el mismo estado que usa `bajar_candidatas`.
            # `ingerir_nuevas` arma `pedido_de` desde ahi para revalidar identidad antes de
            # tocar la DB; sin esta linea el pedido llegaba como "?" y las normas se
            # rechazaban por identidad SIN decir por que. Paso con el DS 44 y el DS 88:
            # bajados bien (dominio 0.579 y 0.591) y descartados en silencio al ingerir.
            est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
            est[f"{tipo.upper()}-{num}"] = {"estado": "resuelto", "id_norma": nid,
                                            "citas": 0, "descargado": True,
                                            "chars": len(d.texto_completo),
                                            "origen": "bajar_por_id"}
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1))
            print(f"    guardado -> {out}  (registrado como {tipo.upper()}-{num})", flush=True)
            await asyncio.sleep(15)      # throttle: BCN devuelve 429 por cuota


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1:]))
