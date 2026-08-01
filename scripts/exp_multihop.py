"""Prueba multi-hop (Adaptive-RAG / self-ask) sobre las 4 fallas de RETRIEVAL coloquial.
El LLM descompone la query (entidad implícita → aspecto), reformula a pregunta legal directa,
y se mide si el gold entra al pool con el 4B. ¿Rescata 212 (multi-hop real) y/o los otros?

Dos fases para evitar swap Ollama 9b↔4b: 1) descompone todas con 9b, 2) embebe todas con 4b.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_multihop
"""
import json, urllib.request, math
from src.components.llm import get_llm_provider
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

QS = [("258171", "87", "¿Cada cuánto se sientan a planear qué torres nuevas hay que construir y quién lo hace?"),
      ("258171", "118", "¿Hay un tope de ganancia que les permiten cobrar a los dueños de las líneas grandes?"),
      ("1149788", "2", "quiero poner paneles en el techo de mi casa, ¿hay un tope de tamaño para que entre en este beneficio de inyectar a la red?"),
      ("258171", "212", "Ese grupo que resuelve las peleas entre las empresas y el operador, ¿quién paga lo que cuesta tenerlo funcionando?")]

DECOMP = (
    "Eres experto en normativa eléctrica chilena (LGSE y reglamentos). La siguiente pregunta "
    "coloquial puede referirse a una ENTIDAD/concepto implícito y preguntar un ASPECTO de él.\n"
    "Paso 1: identifica la entidad o concepto legal exacto al que se refiere (si la query lo "
    "describe sin nombrarlo).\n"
    "Paso 2: reformula como UNA pregunta legal directa y específica que nombre esa entidad y el "
    "aspecto preguntado. Sin inventar números de ley.\n"
    "Devuelve SOLO la pregunta reformulada, una línea.\n"
    "Pregunta: {q}\nPregunta legal directa:"
)


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


def rank_of(order, gold):
    for i, k in enumerate(order, 1):
        if k == gold:
            return i
    return None


def main():
    llm = get_llm_provider()
    # Fase 1: descomposición (9b)
    ref = {}
    for nm, ar, q in QS:
        r = llm.generate(DECOMP.format(q=q), max_tokens=80)
        ref[(nm, ar)] = r.text.strip().splitlines()[0].strip()
        print(f"[decomp] {nm}/{ar}: {ref[(nm,ar)][:90]}", flush=True)
    # Fase 2: embed (4b) original vs reformulada → rank del gold
    print("\n=== rank del gold (4B-1024, top-50) ===", flush=True)
    for nm, ar, q in QS:
        gold = (nm, _normalize_art(ar))
        ro = rank_of(ranking("embedding_4b_1024", trunc(ollama_embed("qwen3-embedding:4b", q))), gold)
        rr = rank_of(ranking("embedding_4b_1024", trunc(ollama_embed("qwen3-embedding:4b", ref[(nm, ar)]))), gold)
        print(f"  {nm}/{ar}: original rank={ro or '>50'}  multihop rank={rr or '>50'}  "
              f"{'RESCATA' if (rr and rr<=10 and (not ro or ro>10)) else ''}", flush=True)


if __name__ == "__main__":
    main()
