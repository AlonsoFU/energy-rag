"""E0/E1 — DESCUBRIR normativa nueva relevante para la Subgerencia de Mercados.

El monitor (B4) detecta cambios en normas que YA están. Esto responde la otra mitad:
**¿qué normativa existe que todavía no tenemos?**

Tres fuentes, de más barata a más cara. Todas terminan en el MISMO filtro, así que el criterio
de dominio es uno solo y es el del usuario (similitud >= 0.30 contra las funciones de la
subgerencia — ver `frontera_mercados.py`):

  1. CITAS COLGANTES (gratis, offline)
     Normas citadas desde el corpus que no están en él. Ya extraídas por B3.4:
     `referencias.tipo_relacion='remite'` resuelve 797; las que NO resuelven son candidatas.
     Señal fuerte: si el articulado del dominio la cita, importa.

  2. VINCULACIONES BCN (red, throttled)
     `norma_vinculacion` trae las normas que MODIFICAN o DEROGAN a las del corpus. Una norma
     nueva que modifica una que tenemos es, por definición, relevante.

  3. CRAWLERS DE ORGANISMO (red, pendiente)
     CNE / SEC / CEN publican resoluciones que BCN no indexa (NTCO, instructivos, IVTE).
     Sin esto el corpus no cubre la operación diaria. NO implementado todavía.

Salida: `docs/descubrimiento-pendiente.md` — ranking de candidatas con su evidencia, para que
el usuario apruebe qué se baja. **No descarga nada por su cuenta.**

  PYTHONPATH=. venv/bin/python -m scripts.descubrir_normativa
"""
import collections
import math
import re
from pathlib import Path

from psycopg.rows import dict_row

from src.components.vectorstore import with_connection
from src.pipelines.retrieve import _embed_4b_query
from scripts.frontera_mercados import DOMINIO

CORTE = 0.30


def _v(t):
    e = _embed_4b_query(t)
    if not e:
        return None
    s = e[:1024]
    n = math.sqrt(sum(x * x for x in s)) or 1.0
    return [x / n for x in s]


def main():
    ref = _v(re.sub(r"\s+", " ", DOMINIO).strip())

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id_norma, tipo, numero, titulo,
                              coalesce((metadata->>'fuera_de_dominio')='true', false) AS fuera
                       FROM normas""")
        dentro = {r["id_norma"]: r for r in cur.fetchall()}
        # fuente 2: quien modifica/deroga a las nuestras
        cur.execute("""SELECT origen, destino, tipo_relacion FROM norma_vinculacion""")
        vinc = cur.fetchall()

    # --- fuente 1: citas colgantes (se recalculan aca para no depender del orden de scripts)
    from scripts.resolver_citas_normas import PAT, TIPO, _num, _tipo
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT a.id_norma, a.texto FROM articulos a
                       JOIN normas n ON n.id_norma = a.id_norma
                       WHERE a.texto IS NOT NULL
                         AND coalesce((n.metadata->>'fuera_de_dominio')='true', false) = false""")
        arts = cur.fetchall()
    cat = collections.defaultdict(list)
    for n in dentro.values():
        cat[(str(n["tipo"]).upper(), _num(n["numero"]))].append(n["id_norma"])

    colgantes = collections.Counter()
    for a in arts:
        for m in PAT.finditer(a["texto"] or ""):
            t = _tipo(m.group(1))
            if not t:
                continue
            k = (t, _num(m.group(2)))
            if not cat.get(k):
                colgantes[k] += 1

    # --- fuente 2: vinculaciones a normas que no tenemos
    faltan_vinc = collections.Counter()
    for v in vinc:
        if v["origen"] not in dentro:
            faltan_vinc[(v["origen"], v["tipo_relacion"])] += 1

    print(f"fuente 1 — citas colgantes desde el dominio : {len(colgantes)} normas distintas, "
          f"{sum(colgantes.values())} citas", flush=True)
    print(f"fuente 2 — normas que nos modifican/derogan y NO tenemos: "
          f"{len({o for o, _t in faltan_vinc})}", flush=True)
    print(f"fuente 3 — crawlers CNE/SEC/CEN: NO IMPLEMENTADO (bloquea la NTCO)", flush=True)

    L = ["# Descubrimiento pendiente — normativa que el corpus NO tiene", "",
         "Generado por `scripts/descubrir_normativa.py`. **No descarga nada**: es una lista",
         "para aprobar. El filtro de dominio es el mismo del corte de frontera (>= 0.30).", "",
         "## Fuente 1 — citadas desde el dominio y ausentes", "",
         "Señal más fuerte que hay: el articulado que sí es del dominio las cita.",
         "⚠️ Solo se cuentan citas desde normas NO marcadas `fuera_de_dominio`, para que la",
         "Ley de Tránsito no arrastre sus propias referencias al ranking.", "",
         "| tipo | número | veces citada |", "|---|---|---|"]
    for (t, n), v in colgantes.most_common(80):
        L.append(f"| {t} | {n} | {v} |")

    L += ["", "## Fuente 2 — normas que MODIFICAN o DEROGAN a las nuestras y faltan", "",
          "Si una norma nueva modifica una que tenemos, es relevante por definición.", "",
          "| id_norma BCN | relación | veces |", "|---|---|---|"]
    for (o, tr), v in faltan_vinc.most_common(60):
        L.append(f"| {o} | {tr} | {v} |")

    L += ["", "## Fuente 3 — crawlers de organismo (PENDIENTE)", "",
          "CNE · SEC · CEN publican resoluciones que BCN no indexa. **Sin esto el corpus no",
          "cubre la operación diaria de la subgerencia** (la NTCO fija los plazos del Informe",
          "de Valorización de Transferencias Económicas). No implementado."]
    out = Path("docs/descubrimiento-pendiente.md")
    out.write_text("\n".join(L) + "\n")
    print(f"\nescrito {out}", flush=True)
    print("\ntop citadas y ausentes:", flush=True)
    for (t, n), v in colgantes.most_common(10):
        print(f"   {v:>4}x  {t} {n}", flush=True)


if __name__ == "__main__":
    main()
