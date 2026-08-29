"""B3.4 (RE-DEFINIDO) — citas norma→norma desde el TEXTO, y candidatas de frontera.

El item original del plan decia "resolver `referencias.destino_norma_id` (5687 filas)".
**Estaba mal diagnosticado.** Esas 5687 filas ya apuntan a algo y NO son citas norma→norma:

    cita                  5170   -> destino_concepto_id (terminos del glosario)
    referencia_implicita   235   -> destino_articulo_id (articulo precedente)
    define_termino         282   -> destino_concepto_id
    sin destino              0

`destino_norma_id` esta vacio porque esas referencias son intra-corpus. Las citas a OTRAS
normas nunca se extrajeron: viven en el texto de los articulos, sin tocar.

Este script las extrae (3066 detectadas) y las resuelve contra el catalogo real.

SOBRE EL REGEX (regla del proyecto): aca el regex **solo propone candidatos**; quien decide es
el **catalogo de normas** — una cita cuenta como resuelta unicamente si (tipo, numero) matchea
una norma que existe en la DB. El regex no clasifica ni interpreta, y no hay lista de normas
hardcodeada. Mejora futura con GPU libre: NER con el LLM local y comparar cobertura.

Salidas:
  1. `referencias` con tipo_relacion='remite' y `destino_norma_id` resuelto (idempotente).
     'remite' porque el CHECK de la tabla solo admite un enum fijo y 'cita' ya esta ocupado
     por las 5170 referencias a CONCEPTOS del glosario — mezclarlas las volveria indistinguibles.
     Solo se llena `origen_articulo_id`: la tabla tiene un CHECK que exige exactamente uno
     de (origen_articulo_id, origen_norma_id). La norma origen sale por JOIN a `articulos`.
  2. `docs/frontera-candidatas.md` — las normas citadas que NO estan en el corpus, ordenadas
     por veces citada y **separando si las cita el dominio electrico o una norma ajena**.
     Ese reporte es el insumo de la decision 0.2 (frontera del corpus), que es del usuario.

  PYTHONPATH=. venv/bin/python -m scripts.resolver_citas_normas [--escribir]
"""
import collections
import re
import sys
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection

# el regex PROPONE; el catalogo DISPONE
PAT = re.compile(
    r"\b(ley|decreto\s+supremo|decreto\s+con\s+fuerza\s+de\s+ley|decreto\s+ley|decreto|"
    r"resoluci[oó]n\s+exenta|resoluci[oó]n)\s+(?:n[°ºo]\.?\s*)?([\d\.]{1,9})\b", re.I)
TIPO = {"ley": "LEY", "decreto supremo": "DECRETO", "decreto": "DECRETO",
        "decreto con fuerza de ley": "DFL", "decreto ley": "DL",
        "resolucion": "RESOLUCION", "resolucion exenta": "RESOLUCION"}
# materias fuera del dominio electrico (se detectan por TITULO, no por lista de ids)
AJENA = re.compile(r"tr[áa]nsito|transporte\s+p[úu]blico|obras\s+p[úu]blicas|procesal\s+penal|"
                   r"insolvencia|reemprendimiento|copropiedad|urbanismo|construcciones", re.I)


# El TIPO de relacion lo dice el verbo que introduce la cita, no hay que inferirlo. Las 2204
# citas norma->norma estaban todas como `remite` generico, que no distingue "esta norma
# DEROGA a aquella" de "la menciona al pasar" -- y esa diferencia es la que hace util el
# grafo: pedido del usuario, "mapea bien la norma y sus relaciones".
#
# Se mira la ventana ANTES de la cita: ahi va el verbo. El enum de la tabla ya admitia
# 'modifica', 'deroga' y 'complementa'; estaban sin usar.
VERBO_TIPO = [
    (re.compile(r"der[óo]g(?:ase|uese|anse|uense)|queda\s+derogad", re.I), "deroga"),
    (re.compile(r"modif[íi]case|introd[úu]cense|reempl[áa]zase|sustit[úu]yese|agr[ée]gase|"
                r"incorp[óo]rase|interc[áa]lase|el[íi]minase|sup[rr][íi]mese", re.I), "modifica"),
    (re.compile(r"apru[ée]base\s+el\s+(?:siguiente\s+)?reglamento|"
                r"reglamento\s+de\s+(?:la\s+)?(?:ley|decreto)", re.I), "complementa"),
    (re.compile(r"de\s+conformidad|conforme\s+a|seg[úu]n\s+lo\s+dispuesto|"
                r"en\s+virtud\s+de|de\s+acuerdo\s+a", re.I), "aplica"),
]
VENTANA = 90        # caracteres antes de la cita donde vive el verbo

# "Modificase el articulo 3º de la ley Nº 18.410" -- el articulo va ANTES de la norma, entre
# el verbo y la cita. Si ese articulo existe en la DB, la relacion apunta a EL y no a la norma
# entera: saber que LEY 21194 toca el articulo 118 del DFL 4 es mucho mas util que saber que
# "lo modifica" a secas. El CHECK de la tabla admite un solo destino, asi que el articulo gana
# cuando se puede resolver.
ART_TOCADO = re.compile(
    r"art[íi]culos?\s+(?P<art>\d{1,3}[°ºª]?(?:\s*-\s*\d+)?(?:\s*(?:bis|ter|quater))?)"
    r"(?P<medio>[^.;]{0,60})$", re.IGNORECASE)


def _art_tocado(texto, ini):
    """Numero de articulo mencionado justo antes de la cita, si lo hay."""
    prev = texto[max(0, ini - 140):ini]
    m = ART_TOCADO.search(prev)
    if not m:
        return None
    # el "medio" no debe cruzar otra norma: "articulo 5 de la ley X, y la ley Y" apuntaria mal
    if re.search(r"\b(ley|decreto|reglamento|resoluci[oó]n)\b", m.group("medio"), re.I):
        return None
    return re.sub(r"[°ºª\s]+", "", m.group("art")).lower()


def _tipo_relacion(texto, ini):
    """Tipo de la relacion segun el verbo que precede a la cita. Default `remite`."""
    prev = texto[max(0, ini - VENTANA):ini]
    for pat, tipo in VERBO_TIPO:
        if pat.search(prev):
            return tipo
    return "remite"


def _num(s):
    return (s or "").replace(".", "").replace(" ", "").lstrip("0") or "0"


def _tipo(raw):
    k = re.sub(r"\s+", " ", raw.lower()).replace("ó", "o")
    return TIPO.get(k)


def main(escribir=False):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, tipo, numero, titulo FROM normas")
        normas = cur.fetchall()
        cur.execute("SELECT id, id_norma, texto FROM articulos WHERE texto IS NOT NULL")
        arts = cur.fetchall()
        cur.execute("""SELECT id, id_norma,
                              lower(replace(replace(replace(numero,'°',''),'º',''),' ','')) k
                       FROM articulos""")
        idx_art = {(r["id_norma"], r["k"]): r["id"] for r in cur.fetchall()}

    cat = collections.defaultdict(list)
    for n in normas:
        cat[(str(n["tipo"]).upper(), _num(n["numero"]))].append(n["id_norma"])
    meta = {n["id_norma"]: n for n in normas}
    ajenas = {n["id_norma"] for n in normas if AJENA.search(n["titulo"] or "")}
    print(f"catalogo: {len(normas)} normas ({len(ajenas)} ajenas al dominio electrico)")

    resueltas, ambiguas = [], 0
    externas = collections.defaultdict(
        lambda: {"total": 0, "desde_electrico": 0, "ejemplo": "", "ctx": []})
    for a in arts:
        for m in PAT.finditer(a["texto"] or ""):
            t = _tipo(m.group(1))
            if not t:
                continue
            k = (t, _num(m.group(2)))
            hits = cat.get(k) or []
            if len(hits) == 1:
                if hits[0] != a["id_norma"]:           # autocitas no aportan al grafo
                    tr = _tipo_relacion(a["texto"] or "", m.start())
                    aid_dest = None
                    if tr in ("modifica", "deroga"):
                        k = _art_tocado(a["texto"] or "", m.start())
                        if k:
                            aid_dest = idx_art.get((hits[0], k))
                    resueltas.append((a["id"], hits[0], m.group(0), tr, aid_dest))
            elif len(hits) > 1:
                ambiguas += 1
            else:
                e = externas[k]
                e["total"] += 1
                if a["id_norma"] not in ajenas:
                    e["desde_electrico"] += 1
                if not e["ejemplo"]:
                    e["ejemplo"] = m.group(0)
                # CONTEXTO de la cita, no solo la cita. El articulado suele nombrar la materia
                # ahi mismo: "Ley N° 21.719, que regula la proteccion de datos personales".
                # Con eso se puede puntuar el dominio SIN bajar la norma -- que es lo que
                # fallo el 25-08: las 4 candidatas mas citadas resultaron ajenas (proteccion
                # de datos, desarrollo social, alta direccion publica, transporte) y se
                # gastaron 4 descargas para descubrirlo.
                if len(e["ctx"]) < 6:
                    txt = a["texto"] or ""
                    e["ctx"].append(re.sub(r"\s+", " ",
                                           txt[max(0, m.start() - 60):m.end() + 180]).strip())

    print(f"citas resueltas a normas del corpus : {len(resueltas)}")
    _con_art = sum(1 for *_x, ad in resueltas if ad is not None)
    print(f"   ...con el ARTICULO tocado resuelto : {_con_art}")
    _por_tipo = collections.Counter(r[3] for r in resueltas)
    for _t, _n in _por_tipo.most_common():
        print(f"     {_t:14} {_n}")
    print(f"ambiguas (>1 candidata)             : {ambiguas}")
    print(f"citadas y NO en el corpus           : {sum(v['total'] for v in externas.values())}"
          f"  ({len(externas)} normas distintas)")
    # Puntaje de dominio del CONTEXTO. Es una señal debil -- mide como habla de la norma quien
    # la cita, no la norma misma -- pero se obtiene sin descargar nada y ordena mucho mejor
    # que el numero de citas, que pone arriba justo las normas transversales.
    try:
        from scripts.frontera_mercados import DOMINIO
        from scripts.marcar_fuera_dominio import _v
        ref = _v(re.sub(r"\s+", " ", DOMINIO).strip())
        for k, v in externas.items():
            if not v["ctx"] or not ref:
                v["dom"] = None
                continue
            b = _v(" ".join(v["ctx"])[:3000])
            v["dom"] = round(sum(x * y for x, y in zip(ref, b)), 3) if b else None
        print("puntaje de dominio del contexto: calculado")
    except Exception as ex:
        for v in externas.values():
            v["dom"] = None
        print(f"puntaje de dominio: no disponible ({type(ex).__name__})")

    solo_e = {k: v for k, v in externas.items() if v["desde_electrico"] > 0}
    print(f"   ...de esas, citadas DESDE el dominio electrico: {len(solo_e)} normas")

    if escribir:
        with with_connection() as c, c.cursor() as cur:
            cur.execute("""DELETE FROM referencias
                           WHERE tipo_relacion IN ('remite','modifica','deroga','complementa','aplica')
                             AND destino_norma_id IS NOT NULL""")
            # el CHECK admite UN solo destino: si se resolvio el articulo, gana el articulo
            cur.executemany(
                """INSERT INTO referencias
                   (origen_articulo_id, destino_norma_id, tipo_relacion,
                    confianza, metodo_extraccion, contexto)
                   VALUES (%s,%s,%s,0.9,'regex',%s)""",
                [(a, d, t, ctx) for a, d, ctx, t, ad in resueltas if ad is None])
            cur.executemany(
                """INSERT INTO referencias
                   (origen_articulo_id, destino_articulo_id, tipo_relacion,
                    confianza, metodo_extraccion, contexto)
                   VALUES (%s,%s,%s,0.95,'regex',%s)""",
                [(a, ad, t, ctx) for a, d, ctx, t, ad in resueltas if ad is not None])
            c.commit()
        print(f"escritas {len(resueltas)} filas remite en `referencias`")

    out = Path("docs/frontera-candidatas.md")
    # Se ordena por DOMINIO y despues por citas. Al reves (por citas) las cuatro primeras
    # candidatas eran normas ajenas citadas de paso.
    orden = sorted(externas.items(),
                   key=lambda kv: (-(kv[1].get("dom") or 0), -kv[1]["desde_electrico"]))
    L = ["# Candidatas de frontera — normas citadas que NO están en el corpus",
         "",
         "Generado por `scripts/resolver_citas_normas.py`. **Insumo de la decisión 0.2**",
         "(frontera del corpus), que es del usuario, no mía.",
         "",
         f"- citas norma→norma detectadas en el texto: **{len(resueltas) + sum(v['total'] for v in externas.values())}**",
         f"- resueltas a normas del corpus: **{len(resueltas)}**",
         f"- apuntan fuera del corpus: **{sum(v['total'] for v in externas.values())}** "
         f"({len(externas)} normas distintas)",
         "",
         "`desde_elec` = veces citada desde una norma del dominio eléctrico (excluye las ajenas:",
         "tránsito, obras públicas, procesal penal…). **Es la columna que importa** — una norma",
         "citada solo por la Ley de Tránsito no entra al corpus eléctrico.",
         "",
         "**Ordenadas por `dom`**, no por citas. `dom` = parecido del CONTEXTO de la cita con",
         "las funciones de la subgerencia. Es señal débil —mide cómo habla de la norma quien la",
         "cita, no la norma misma— pero se obtiene sin descargar nada, y ordenar por citas ponía",
         "arriba justo las transversales: protección de datos (85 citas, dominio real 0.259),",
         "desarrollo social (65 · 0.191), alta dirección pública (55 · 0.295).",
         "",
         "| dom | tipo | número | desde_elec | total | ejemplo |",
         "|---|---|---|---|---|---|"]
    for (t, n), v in orden[:120]:
        d = f"{v['dom']:.3f}" if v.get("dom") is not None else "—"
        L.append(f"| {d} | {t} | {n} | **{v['desde_electrico']}** | {v['total']} | {v['ejemplo']} |")
    L += ["", f"_({len(orden)} normas distintas en total; se listan las 120 más citadas)_"]
    out.write_text("\n".join(L) + "\n")
    print(f"escrito {out}")


if __name__ == "__main__":
    main(escribir="--escribir" in sys.argv)
