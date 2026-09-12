"""exp #69b -- REPARAR ARTICULOS cortados por las notas BCN, sin re-ingestar.

Hallazgo (2026-09-06, viene del spot-check de #68): ARTICULO_PATTERN acepta "Art. N" a inicio
de linea, y las notas BCN traen justo eso ("Ley 20936 / Art. 1 N° 25 / D.O. 20.07.2016"). La
nota partia el articulo: el Art. 165 de la LGSE quedaba en "- Dentro" (8 chars) y el resto
caia en un articulo FANTASMA "1". En la LGSE (la norma mas citada): 450 filas, 163 basura.
Corpus: 338 articulos no derogados de < 60 chars. El juez de #68 leia esas filas y decia
NO_SOPORTADA por respuestas correctas (11 de 16). Y retrieval no puede encontrar lo que no esta.

Fix en el parser (`quitar_notas_bcn` ANTES de segmentar, iterado para notas apiladas).
Medido parser viejo (HEAD) -> nuevo sobre las 124 normas, clave normalizada: 3908 iguales,
908 GANAN texto, 144 encogen (fantasmas que habian tragado al siguiente, o transitorio que
pisaba al permanente: ahora gana el encabezado fuerte ".-"/":" y en empate el primero), 65
desaparecen, 108 aparecen. Articulos < 60 chars: 486 -> 152 (49 son "(DEROGADO)" legitimos).

Este script lleva eso a la DB SIN tocar ids (obligaciones, referencias y definiciones cuelgan
de articulos.id):
  BASURA     fila < 60 chars no derogada, el parser trae el texto real   -> UPDATE texto
  EXTENSION  el texto nuevo contiene el viejo y es mas largo             -> UPDATE texto
  LIMPIEZA   mismo arranque, largo >= 80 %, solo cambian notas/espacios   -> UPDATE texto
  CABEZA     mismo final, la DB arranca en residuo de nota (cabeza cortada) -> UPDATE texto
  RECORTE    mismo arranque, la DB se habia tragado los articulos siguientes -> UPDATE texto
  REVISAR    DB y parser no coinciden en que es el articulo N            -> NO se toca, se lista
             (transitorios que pisan al permanente, referencias a inicio de linea: bug previo)
  FANTASMA   fila cuya clave no existe en el parser, o fila de mas de una
             clave duplicada                                              -> metadata.fantasma
             (el retrieval las excluye igual que duplicado_de)
  NUEVO      articulo del parser que no esta en la DB                     -> INSERT
Los articulos con UPDATE o INSERT se RE-FRAGMENTAN (HierarchicalChunker, mismo contextual_text
que sus fragmentos viejos) y se re-embeben con 4B -> embedding_4b_1024 (la columna que usa
produccion) y 0.6B -> embedding. tsv es GENERATED. No toca fragmentos_inciso (experimental),
fragmentos_definicion ni obligacion.

Respaldo: articulos_bak_69b (tabla entera), fragmentos_bak_69b (filas afectadas), y
data/eval/results/reparar_69b_aplicado.json con los ids insertados. `--revertir` deshace todo.

Uso:
  PYTHONPATH=. venv/bin/python -m scripts.reparar_articulos            # simulacion + informe
  PYTHONPATH=. venv/bin/python -m scripts.reparar_articulos --apply
  PYTHONPATH=. venv/bin/python -m scripts.reparar_articulos --revertir
"""
import argparse, json, math, re, sys, time
from pathlib import Path
from src.parsers.norm_structure_parser import NormStructureParser as P
from src.storage.connection import with_connection
from scripts.mark_derogados import es_derogado

BAK = "69b"
APLICADO = Path("data/eval/results/reparar_69b_aplicado.json")
INFORME = Path("data/eval/results/reparar_69b_informe.json")
JUNK = 60


def nz(s):
    s = P.quitar_notas_bcn(s or "")
    s = P.MODIFICACION_PATTERN.sub("", s)
    s = re.sub(r"[\s\xa0]+", " ", s).strip().lower()
    s = re.sub(r"^(art[íi]culo|art\.)\s*[\w°ºª\- ]{1,14}?\s*[:\.\-]+\s*", "", s)
    return re.sub(r"^[\-\.\s:]+", "", s)


def key(n):
    return n.replace("°", "").replace("º", "").replace("ª", "").lower().strip()


def clasificar(cur):
    """Devuelve dict con listas por clase. No escribe nada."""
    p = P()
    out = dict(igual=[], update=[], revisar=[], fantasma=[], nuevo=[])
    cur.execute("SELECT id_norma, titulo, texto_completo FROM normas WHERE texto_completo IS NOT NULL")
    for nid, tit, t in cur.fetchall():
        parsed = p.parse(t, nid).articulos
        arts = {key(k): a for k, a in parsed.items()}
        # cuerpo de todos los articulos nuevos: un fantasma es una fila cuyo texto vive ahora
        # dentro de un articulo real (o basura). Si no, es un articulo que el parser NO ve
        # ("primero transitorio", "único" de ingestas viejas) y se deja quieto.
        cuerpo = " ".join(nz(a.texto) for a in parsed.values())
        def contenido(tx, en=None, minimo=1):
            # minimo=1: alguna ventana vive en `en`. minimo<1: esa fraccion de las ventanas.
            en = cuerpo if en is None else en
            vent = [v for v in ([tx[i:i + 70] for i in range(0, max(len(tx) - 70, 1), 120)] or [tx])
                    if len(v) >= 50]
            hits = sum(1 for v in vent if v in en)
            return hits >= 1 if minimo >= 1 else (vent and hits / len(vent) >= minimo)

        def arranque_roto(r, tx):
            # residuo de nota al inicio ("n° 2 d.o. 09.02.2017 ..."), numero "107 D"
            # (de "Art. 107 / D.O ..."), o arranca a mitad de frase
            return (re.search(r"\d{2}\.\d{2}\.\d{4}", tx[:40]) is not None
                    or r["numero"].lower().endswith(" d")
                    or re.match(r"(de|del|y|o|que|a|en) ", tx) is not None)

        def es_fantasma(r, con_par):
            tx = nz(r["texto"])
            if len(r["texto"] or "") < JUNK:
                return True
            # FIX 2026-09-10: no basta con que el texto viva en `cuerpo` (todo lo parseado).
            # Si solo vive en un TRANSCRITO que no se inserta, marcarlo fantasma lo saca de
            # retrieval y el texto queda INALCANZABLE. Medido: 18 de 299 quedaron asi, y las
            # citas inexistentes de dev saltaron de 4 a 18. Mismo chequeo que ya tenia RECORTE.
            if not contenido(tx, cuerpo_db):
                return False
            # fila de mas de una clave que SI existe en el parser: basta que su texto viva
            # dentro de un articulo nuevo. Fila de clave que el parser no ve ("undécimo",
            # "1º transitorio"): ademas tiene que verse rota, si no se deja quieta.
            return contenido(tx) and (con_par or arranque_roto(r, tx))
        cur.execute("SELECT id, numero, texto, derogado, metadata FROM articulos WHERE id_norma=%s", (nid,))
        g = {}
        for i, n, tx, d, md in cur.fetchall():
            g.setdefault(key(n), []).append(dict(id=i, numero=n, texto=tx, derogado=d, meta=md or {}))
        # cuerpo que QUEDA VISIBLE tras aplicar: todo lo no transcrito (igual/update/nuevo) mas
        # los transcritos que YA estaban en la DB. Si un texto solo vive fuera de aqui, sacarlo
        # de retrieval lo pierde. Lo usan RECORTE y FANTASMA.
        cuerpo_db = " ".join(nz(a.texto) for kk, a in arts.items()
                             if not a.es_transcrito or kk in g)
        for k, filas in g.items():
            filas.sort(key=lambda r: -len(r["texto"] or ""))
            principal, resto = filas[0], filas[1:]
            for r in resto:
                d = dict(id=r["id"], norma=nid, numero=r["numero"], duplicado_de=principal["id"],
                         chars=len(r["texto"] or ""), db=nz(r["texto"])[:80])
                out["fantasma" if es_fantasma(r, k in arts) else "revisar"].append(d)
            if k not in arts:
                d = dict(id=principal["id"], norma=nid, numero=principal["numero"], duplicado_de=None,
                         chars=len(principal["texto"] or ""), db=nz(principal["texto"])[:80])
                out["fantasma" if es_fantasma(principal, False) else "revisar"].append(d)
                continue
            a_ = arts[k]
            if a_.es_transcrito:
                out["igual"].append(principal["id"]); continue
            a, b = nz(principal["texto"]), nz(a_.texto)
            base = dict(id=principal["id"], norma=nid, numero=principal["numero"],
                        chars_db=len(principal["texto"] or ""), chars_nuevo=len(a_.texto))
            if a == b or (abs(len(a) - len(b)) <= 0.05 * max(len(a), len(b)) and a[:60] == b[:60]):
                out["igual"].append(principal["id"])
            elif len(principal["texto"] or "") < JUNK and not principal["derogado"]:
                out["update"].append(dict(base, clase="BASURA", texto=a_.texto))
            elif a[:80] in b and len(b) >= len(a):
                out["update"].append(dict(base, clase="EXTENSION", texto=a_.texto))
            elif a[:40] == b[:40] and len(b) >= 0.8 * len(a):
                out["update"].append(dict(base, clase="LIMPIEZA", texto=a_.texto))
            elif a[-80:] == b[-80:] and len(b) >= 0.8 * len(a) and arranque_roto(principal, a):
                # la nota partio la CABEZA: "Las concesiones de" quedo en el articulo anterior
                # y este arranca en "D.O. 13.09.1982 servicio publico..."
                out["update"].append(dict(base, clase="CABEZA", texto=a_.texto))
            elif a[:80] == b[:80] and len(b) < len(a) and contenido(a[len(b):], cuerpo_db, minimo=0.9):
                # la fila de la DB se habia tragado los articulos siguientes (16 bis, ter...),
                # que ahora existen aparte: se RECORTA
                out["update"].append(dict(base, clase="RECORTE", texto=a_.texto))
            else:
                out["revisar"].append(dict(base, db=a[:80], nuevo=b[:80]))
        for k, a_ in arts.items():
            if k not in g and not a_.es_transcrito and len(a_.texto) >= 1:
                out["nuevo"].append(dict(norma=nid, numero=k, chars=len(a_.texto), texto=a_.texto,
                                         numero_original=next(kk for kk in parsed if key(kk) == k)))
    return out


def informe(c):
    from collections import Counter
    upd = Counter(u["clase"] for u in c["update"])
    print(f"igual {len(c['igual'])} | update {len(c['update'])} {dict(upd)} | revisar {len(c['revisar'])} "
          f"| fantasma {len(c['fantasma'])} | nuevo {len(c['nuevo'])}")
    por = Counter();
    for u in c["update"]: por[u["norma"]] += 1
    print("  update por norma:", por.most_common(8))
    por = Counter(r["norma"] for r in c["revisar"]); print("  revisar por norma:", por.most_common(8))


def _ctx_prefix(cur, aid, tit, numero):
    cur.execute("SELECT contextual_text FROM fragmentos WHERE articulo_id=%s ORDER BY chunk_index LIMIT 1", (aid,))
    r = cur.fetchone()
    if r and r[0] and " — Artículo " in r[0]:
        return r[0].split(" — Artículo ")[0] + f" — Artículo {numero}. "
    return f"{tit} — Artículo {numero}. "


def refragmentar(cur, aid, nid, numero, texto, emb06, chunker, embed4b):
    cur.execute("SELECT titulo FROM normas WHERE id_norma=%s", (nid,))
    tit = (cur.fetchone() or [""])[0] or ""
    pref = _ctx_prefix(cur, aid, tit, numero)
    cur.execute("DELETE FROM fragmentos WHERE articulo_id=%s", (aid,))
    n = 0
    for ch in chunker.chunk(texto):
        ctx = pref + ch.text
        e4 = embed4b(ctx) or []
        s4 = e4[:1024]
        nn = math.sqrt(sum(x * x for x in s4)) or 1.0
        cur.execute("""INSERT INTO fragmentos (articulo_id, chunk_index, text, contextual_text,
                       embedding, embedding_4b_1024, token_count) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (aid, ch.chunk_index, ch.text, ctx, emb06.embed([ctx])[0],
                     [x / nn for x in s4] if s4 else None, ch.token_count))
        n += 1
    return n


def aplicar(c):
    from src.components.chunker import HierarchicalChunker
    from src.components.embedder import Qwen3Embedder
    from src.pipelines.retrieve import _embed_4b_query
    emb06, chunker = Qwen3Embedder(), HierarchicalChunker()
    t0 = time.time()
    with with_connection() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM information_schema.tables WHERE table_name='articulos_bak_{BAK}'")
        if cur.fetchone():
            print("ya hay respaldo articulos_bak_69b: revertir antes de volver a aplicar"); return
        ids_upd = [u["id"] for u in c["update"]]
        ids_fan = [f["id"] for f in c["fantasma"]]
        cur.execute(f"CREATE TABLE articulos_bak_{BAK} AS SELECT id, numero, texto, metadata FROM articulos")
        cur.execute(f"CREATE TABLE fragmentos_bak_{BAK} AS SELECT * FROM fragmentos WHERE articulo_id = ANY(%s)", (ids_upd,))
        print(f"respaldo: articulos todas, fragmentos {cur.rowcount} filas", flush=True)
        for f in c["fantasma"]:
            md = {"fantasma": "69b"}
            if f["duplicado_de"]:
                md["duplicado_de"] = f["duplicado_de"]
            cur.execute("UPDATE articulos SET metadata = coalesce(metadata,'{}'::jsonb) || %s::jsonb, "
                        "updated_at=now() WHERE id=%s", (json.dumps(md), f["id"]))
        conn.commit()
        print(f"fantasmas marcados: {len(ids_fan)}", flush=True)
        nuevos = []
        nfr = 0
        for i, u in enumerate(c["update"]):
            der = es_derogado(u["texto"])
            cur.execute("UPDATE articulos SET texto=%s, derogado=%s, updated_at=now() WHERE id=%s",
                        (u["texto"], der, u["id"]))
            if not der:
                nfr += refragmentar(cur, u["id"], u["norma"], u["numero"], u["texto"], emb06, chunker, _embed_4b_query)
            if (i + 1) % 50 == 0:
                conn.commit(); print(f"  update {i+1}/{len(c['update'])} frags {nfr} {time.time()-t0:.0f}s", flush=True)
        conn.commit()
        for i, n in enumerate(c["nuevo"]):
            # "- (DEROGADO)" entra como articulo derogado (misma regla que mark_derogados) y
            # sin fragmentos: retrieval ya excluye derogados
            der = es_derogado(n["texto"])
            cur.execute("INSERT INTO articulos (id_norma, numero, texto, derogado) VALUES (%s,%s,%s,%s) RETURNING id",
                        (n["norma"], n["numero_original"], n["texto"], der))
            aid = cur.fetchone()[0]; nuevos.append(aid)
            if not der:
                nfr += refragmentar(cur, aid, n["norma"], n["numero_original"], n["texto"], emb06, chunker, _embed_4b_query)
        conn.commit()
        APLICADO.write_text(json.dumps(dict(update=ids_upd, fantasma=ids_fan, nuevos=nuevos,
                                            fecha="2026-09-06"), indent=1))
        print(f"APLICADO: {len(ids_upd)} updates, {len(nuevos)} nuevos, {nfr} fragmentos, {time.time()-t0:.0f}s")


def revertir():
    a = json.loads(APLICADO.read_text())
    with with_connection() as conn:
        cur = conn.cursor()
        if a["nuevos"]:
            cur.execute("DELETE FROM fragmentos WHERE articulo_id = ANY(%s)", (a["nuevos"],))
            cur.execute("DELETE FROM obligacion WHERE articulo_id = ANY(%s)", (a["nuevos"],))
            cur.execute("DELETE FROM articulos WHERE id = ANY(%s)", (a["nuevos"],))
        cur.execute("DELETE FROM fragmentos WHERE articulo_id = ANY(%s)", (a["update"],))
        # `tsv` y `tsv_aug` son GENERATED ALWAYS: un `SELECT *` las incluye y Postgres rechaza
        # el INSERT ("cannot insert a non-DEFAULT value into column tsv"). Se listan las
        # columnas reales para que la restauracion no dependa del orden ni de las generadas.
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_name='fragmentos' AND is_generated <> 'ALWAYS'
                       ORDER BY ordinal_position""")
        cols = ", ".join(f'"{c[0]}"' for c in cur.fetchall())
        cur.execute(f"INSERT INTO fragmentos ({cols}) SELECT {cols} FROM fragmentos_bak_{BAK}")
        n_fr = cur.rowcount
        cur.execute(f"UPDATE articulos a SET texto=b.texto, metadata=b.metadata, updated_at=now() "
                    f"FROM articulos_bak_{BAK} b WHERE b.id=a.id AND a.id = ANY(%s)",
                    (a["update"] + a["fantasma"],))
        cur.execute(f"DROP TABLE fragmentos_bak_{BAK}"); cur.execute(f"DROP TABLE articulos_bak_{BAK}")
        cur.execute("SELECT setval('fragmentos_id_seq', (SELECT max(id) FROM fragmentos))")
        conn.commit()
    APLICADO.rename(APLICADO.with_suffix(".revertido.json"))
    print(f"REVERTIDO: {len(a['update'])} textos, {len(a['fantasma'])} fantasmas, {len(a['nuevos'])} nuevos borrados, {n_fr} fragmentos restaurados")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revertir", action="store_true")
    args = ap.parse_args()
    if args.revertir:
        revertir(); sys.exit()
    with with_connection() as conn:
        c = clasificar(conn.cursor())
    informe(c)
    INFORME.write_text(json.dumps({k: (v if k != "igual" else len(v)) for k, v in c.items()},
                                  ensure_ascii=False, indent=1, default=str))
    print(f"informe: {INFORME}")
    if args.apply:
        aplicar(c)
    else:
        print("(simulacion; --apply para escribir)")
