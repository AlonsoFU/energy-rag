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

    cat = collections.defaultdict(list)
    for n in normas:
        cat[(str(n["tipo"]).upper(), _num(n["numero"]))].append(n["id_norma"])
    meta = {n["id_norma"]: n for n in normas}
    ajenas = {n["id_norma"] for n in normas if AJENA.search(n["titulo"] or "")}
    print(f"catalogo: {len(normas)} normas ({len(ajenas)} ajenas al dominio electrico)")

    resueltas, ambiguas = [], 0
    externas = collections.defaultdict(lambda: {"total": 0, "desde_electrico": 0, "ejemplo": ""})
    for a in arts:
        for m in PAT.finditer(a["texto"] or ""):
            t = _tipo(m.group(1))
            if not t:
                continue
            k = (t, _num(m.group(2)))
            hits = cat.get(k) or []
            if len(hits) == 1:
                if hits[0] != a["id_norma"]:           # autocitas no aportan al grafo
                    resueltas.append((a["id"], hits[0], m.group(0)))
            elif len(hits) > 1:
                ambiguas += 1
            else:
                e = externas[k]
                e["total"] += 1
                if a["id_norma"] not in ajenas:
                    e["desde_electrico"] += 1
                if not e["ejemplo"]:
                    e["ejemplo"] = m.group(0)

    print(f"citas resueltas a normas del corpus : {len(resueltas)}")
    print(f"ambiguas (>1 candidata)             : {ambiguas}")
    print(f"citadas y NO en el corpus           : {sum(v['total'] for v in externas.values())}"
          f"  ({len(externas)} normas distintas)")
    solo_e = {k: v for k, v in externas.items() if v["desde_electrico"] > 0}
    print(f"   ...de esas, citadas DESDE el dominio electrico: {len(solo_e)} normas")

    if escribir:
        with with_connection() as c, c.cursor() as cur:
            cur.execute("DELETE FROM referencias WHERE tipo_relacion='remite'")
            cur.executemany(
                """INSERT INTO referencias
                   (origen_articulo_id, destino_norma_id, tipo_relacion,
                    confianza, metodo_extraccion, contexto)
                   VALUES (%s,%s,'remite',0.9,'regex',%s)""",
                resueltas)
            c.commit()
        print(f"escritas {len(resueltas)} filas remite en `referencias`")

    out = Path("docs/frontera-candidatas.md")
    orden = sorted(externas.items(), key=lambda kv: (-kv[1]["desde_electrico"], -kv[1]["total"]))
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
         "| tipo | número | desde_elec | total | ejemplo |",
         "|---|---|---|---|---|"]
    for (t, n), v in orden[:120]:
        L.append(f"| {t} | {n} | **{v['desde_electrico']}** | {v['total']} | {v['ejemplo']} |")
    L += ["", f"_({len(orden)} normas distintas en total; se listan las 120 más citadas)_"]
    out.write_text("\n".join(L) + "\n")
    print(f"escrito {out}")


if __name__ == "__main__":
    main(escribir="--escribir" in sys.argv)
