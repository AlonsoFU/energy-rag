"""EXP #59 — clasificar el dominio con un LLM en vez de con la distancia del embedding.

Exp #57 dejó el diagnóstico: el puntaje por embedding **no ordena por materia**. La ley de
biocombustibles puntúa 0.300 y la de acuicultura 0.311, así que ningún umbral las separa —
el orden ya viene mezclado.

Acá el LLM lee el ARTICULADO (no el título: la fórmula burocrática del encabezado legal
chileno es idéntica entre materias) y responde si la norma regula el mercado eléctrico.

**El criterio está fijado en `docs/plan-operacion.md` ANTES de correr**: adoptar sólo si acierta
>= 8 de los 9 casos de control. El embedding acierta 0 de 9 con el corte vigente.

  PYTHONPATH=. venv/bin/python -m scripts.exp_dominio_llm [--todas]

Sin `--todas` corre sólo los 9 controles (barato, ~2 min). Con `--todas`, las 122 normas.
"""
import argparse
import json
import re
import time

from psycopg.rows import dict_row

from src.components.llm import get_llm_provider
from src.components.vectorstore import with_connection
from scripts.frontera_mercados import DOMINIO

MODEL = "ollama/qwen3:30b-a3b"

# Casos de control: fijados en el plan ANTES de correr. Son los casos DIFICILES, donde ya se
# sabe que el embedding falla o acierta por poco -- no una muestra representativa.
CONTROL = {
    "21499": True,  "20698": True,  "21770": True,  "20897": True,
    "20484": False, "838": False,   "20720": False, "20886": False, "18045": False,
}

PROMPT = """Eres un abogado del sector eléctrico chileno. Estas son las funciones de la
subgerencia cuyo corpus normativo estamos armando:

{dominio}

A continuación, el articulado de una norma. Decide si esa norma forma parte de la normativa
que esta subgerencia necesita para operar.

Criterio: entra si regula generación, transmisión, distribución, coordinación, tarificación o
el mercado eléctrico. NO entra si su materia es otra (transporte, acuicultura, insolvencia,
procedimiento civil, mercado de valores), aunque mencione energía de paso.

NORMA: {titulo}

ARTICULADO:
{muestra}

Responde SOLO con un JSON: {{"dentro": true|false, "materia": "<3-6 palabras>"}}"""


def clasificar(llm, titulo, muestra):
    p = PROMPT.format(dominio=re.sub(r"\s+", " ", DOMINIO).strip()[:900],
                      titulo=titulo[:160], muestra=muestra[:2500])
    try:
        r = llm.generate(prompt=p, model=MODEL, temperature=0.0, max_tokens=200)
        txt = getattr(r, "text", "") or ""
    except Exception as ex:
        return None, f"error {type(ex).__name__}"
    m = re.search(r'\{[^{}]*"dentro"[^{}]*\}', txt, re.S)
    if not m:
        return None, "sin json"
    try:
        d = json.loads(m.group(0))
        return bool(d.get("dentro")), str(d.get("materia", ""))[:40]
    except Exception:
        return None, "json invalido"


def main(todas=False):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT n.id_norma, n.tipo, n.numero, n.titulo,
                   (n.metadata->>'similitud_dominio')::float AS sim,
                   coalesce((n.metadata->>'fuera_de_dominio')='true', false) AS fuera,
                   (SELECT string_agg(a.texto, ' ')
                      FROM (SELECT texto FROM articulos
                             WHERE id_norma = n.id_norma AND texto IS NOT NULL
                             ORDER BY id LIMIT 3) a) AS muestra
            FROM normas n ORDER BY n.numero""")
        normas = cur.fetchall()
    if not todas:
        normas = [n for n in normas if str(n["numero"]) in CONTROL]

    llm = get_llm_provider()
    print(f"clasificando {len(normas)} normas con {MODEL}\n", flush=True)
    aciertos = fallos = indef = 0
    for n in normas:
        muestra = (n["muestra"] or n["titulo"] or "")[:2500]
        if len(muestra) < 120:
            print(f"  {n['tipo']} {n['numero']:<8} sin articulado, se saltea", flush=True)
            continue
        t0 = time.time()
        dentro, materia = clasificar(llm, n["titulo"] or "", muestra)
        esperado = CONTROL.get(str(n["numero"]))
        marca = ""
        if esperado is not None:
            if dentro is None:
                indef += 1; marca = "  INDEFINIDO"
            elif dentro == esperado:
                aciertos += 1; marca = "  ok"
            else:
                fallos += 1; marca = f"  FALLA (esperado {'dentro' if esperado else 'fuera'})"
        emb = "dentro" if not n["fuera"] else "fuera"
        print(f"  {n['tipo']} {n['numero']:<8} LLM={'dentro' if dentro else 'fuera' if dentro is not None else '?':<7}"
              f" emb={emb:<7} sim={n['sim'] if n['sim'] is not None else 0:.3f}"
              f"  [{materia}] {time.time()-t0:.0f}s{marca}", flush=True)

    if not todas:
        print(f"\n=== controles: {aciertos} aciertos · {fallos} fallas · {indef} indefinidos "
              f"de {len(CONTROL)} ===")
        print(f"criterio: adoptar si aciertos >= 8  ->  "
              f"{'PASA' if aciertos >= 8 else 'NO PASA'}")
        print("(el embedding acierta 0 de 9 con el corte 0.30 vigente)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--todas", action="store_true")
    main(ap.parse_args().todas)
