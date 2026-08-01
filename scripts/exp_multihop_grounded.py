"""Multi-hop GROUNDED: el salto 1 (identificar la entidad) se ancla a la LISTA REAL de
conceptos del glosario (no la memoria del LLM, que alucinaba 'Centro de Conciliación').
El LLM ELIGE el concepto de la lista → reformula 'aspecto de <concepto>' → retrieval 4B.
Solo LECTURA del glosario (no escribe DB).

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_multihop_grounded
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
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT nombre FROM conceptos WHERE metadata->>'domain_primary'='electricidad' OR metadata->>'domain_primary' IS NULL ORDER BY nombre")
        nombres = [r["nombre"] for r in cur.fetchall()]
    lista = "\n".join(f"- {n}" for n in nombres)
    llm = get_llm_provider()
    prompt_t = (
        "Eres experto en normativa eléctrica chilena. Tienes esta LISTA de conceptos legales:\n"
        f"{lista}\n\n"
        "La pregunta coloquial siguiente describe un concepto SIN nombrarlo. Elige EXACTAMENTE "
        "el nombre de la lista que corresponde, y reformula la pregunta como 'aspecto preguntado "
        "de <ConceptoExacto>'. Si ninguno calza, responde la reformulación más directa posible. "
        "NO inventes conceptos fuera de la lista. Una sola línea.\n"
        "Pregunta: {q}\nReformulación legal:")
    print(f"glosario: {len(nombres)} conceptos", flush=True)
    ref = {}
    for nm, ar, q in QS:
        r = llm.generate(prompt_t.format(q=q), max_tokens=80)
        ref[(nm, ar)] = r.text.strip().splitlines()[0].strip()
        print(f"[grounded] {nm}/{ar}: {ref[(nm,ar)][:95]}", flush=True)
    print("\n=== rank del gold (4B-1024, top-50) ===", flush=True)
    for nm, ar, q in QS:
        gold = (nm, _normalize_art(ar))
        ro = rank_of(ranking("embedding_4b_1024", trunc(ollama_embed("qwen3-embedding:4b", q))), gold)
        rr = rank_of(ranking("embedding_4b_1024", trunc(ollama_embed("qwen3-embedding:4b", ref[(nm, ar)]))), gold)
        flag = "RESCATA" if (rr and rr <= 10 and (not ro or ro > 10)) else ("rompe" if (ro and ro <= 10 and (not rr or rr > 10)) else "")
        print(f"  {nm}/{ar}: original={ro or '>50'}  grounded={rr or '>50'}  {flag}", flush=True)


if __name__ == "__main__":
    main()
