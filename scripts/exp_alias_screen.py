"""Exp #2 — vocabulario controlado coloquial→legal, QUERY-SIDE (archivo, sin DB).

Mapa CURADO {trigger coloquial → término legal a APENDER}. Si la query contiene el
trigger, se concatena el término canónico ANTES de embeber (determinista, no LLM).
El oráculo ya probó que con el término correcto el gold rankea top-2; esto mide si el
mapa lo logra automáticamente. SOLO LECTURA (no escribe DB).

Screen barato: rank del gold (4B-1024, top-50) original vs alias-augmentada.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_alias_screen
"""
import json, urllib.request, math, re
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

# (id_norma, art, query coloquial) — las 4 fallas de RETRIEVAL coloquial
QS = [("258171", "87", "¿Cada cuánto se sientan a planear qué torres nuevas hay que construir y quién lo hace?"),
      ("258171", "118", "¿Hay un tope de ganancia que les permiten cobrar a los dueños de las líneas grandes?"),
      ("1149788", "2", "quiero poner paneles en el techo de mi casa, ¿hay un tope de tamaño para que entre en este beneficio de inyectar a la red?"),
      ("258171", "212", "Ese grupo que resuelve las peleas entre las empresas y el operador, ¿quién paga lo que cuesta tenerlo funcionando?")]

# Mapa CURADO trigger→término. Regex en minúsculas; término legal canónico a apender.
ALIAS = [
    (r"planear|planificar|qu[eé] torres nuevas|construir.*l[ií]nea", "proceso de planificación de la transmisión expansión"),
    (r"tope de ganancia|cu[aá]nto.*pueden cobrar|rentabilidad", "tasa de descuento anualidad del valor de inversión instalaciones de transmisión"),
    (r"tope de tama[nñ]o|paneles.*techo|inyectar a la red|cu[aá]nto.*capacidad", "capacidad instalada equipamiento de generación inyectar excedentes a la red de distribución"),
    (r"grupo que resuelve.*peleas|resuelve.*disputas|dirim", "Panel de Expertos financiamiento presupuesto"),
]


def apply_alias(q, mode="append", weight=2):
    ql = q.lower()
    adds = [term for pat, term in ALIAS if re.search(pat, ql)]
    if not adds:
        return q
    terms = " ".join(adds)
    if mode == "replace":           # el término legal reemplaza la query (como el oráculo)
        return terms
    if mode == "weight":            # query + término repetido weight veces (el término domina)
        return q + " " + " ".join([terms] * weight)
    return q + " " + terms          # append simple


def ollama_embed(model, text):
    d = json.dumps({"model": model, "input": [text]}).encode()
    r = urllib.request.Request("http://localhost:11434/api/embed", data=d, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as x:
        return json.loads(x.read())["embeddings"][0]


def trunc(v, d=1024):
    s = v[:d]; n = math.sqrt(sum(a*a for a in s)) or 1.0
    return [a/n for a in s]


def ranking(col, emb, topn=50):
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT a.id_norma, a.numero FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id
            WHERE f.{col} IS NOT NULL ORDER BY f.{col} <=> %s::vector LIMIT %s""", (str(emb), topn))
        seen, out = set(), []
        for x in cur.fetchall():
            k = (x["id_norma"], _normalize_art(str(x["numero"])))
            if k not in seen:
                seen.add(k); out.append(k)
        return out


def rrf(rankings, k=60):
    sc = {}
    for r in rankings:
        for rank, key in enumerate(r, 1):
            sc[key] = sc.get(key, 0) + 1/(k+rank)
    return [kk for kk in sorted(sc, key=lambda x: -sc[x])]


def rank_of(order, gold):
    for i, k in enumerate(order, 1):
        if k == gold:
            return i
    return None


def main():
    print("=== Exp #2 alias query-side (4B-1024, top-50) ===", flush=True)
    print(f"{'caso':14s} {'orig':>5s} {'replace':>8s} {'UNION':>6s}  nota", flush=True)
    for nm, ar, q in QS:
        gold = (nm, _normalize_art(ar))
        emb_o = ollama_embed("qwen3-embedding:4b", q)
        rk_o = ranking("embedding_4b_1024", trunc(emb_o))
        ro = rank_of(rk_o, gold)
        aug = apply_alias(q, mode="replace")
        fired = aug != q
        if fired:
            rk_a = ranking("embedding_4b_1024", trunc(ollama_embed("qwen3-embedding:4b", aug)))
            ra = rank_of(rk_a, gold)
            ru = rank_of(rrf([rk_o, rk_a]), gold)   # unión: original + alias-replace
        else:
            ra = ru = ro
        fmt = lambda r: (str(r) if r else ">50")
        nota = "RESCATA" if (ru and ru <= 10 and (not ro or ro > 10)) else ("rompe" if (ro and ro <= 10 and (not ru or ru > 10)) else "")
        print(f"{nm+'/'+ar:14s} {fmt(ro):>5s} {fmt(ra):>8s} {fmt(ru):>6s}  {nota}", flush=True)


if __name__ == "__main__":
    main()
