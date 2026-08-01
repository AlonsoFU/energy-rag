"""¿Se puede mejorar el retrieval de 87 y 212? Rank del gold bajo cada embedder y ensembles.
Mide la posición (rank) del artículo gold en top-50 para: 0.6B, 4B, 8B, bge-m3, y RRF de combos.
Si algún embedder/ensemble mete el gold a top-10 → palanca para rescatarlo.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_8712_rank
"""
import json, urllib.request, math
from src.components.embedder import Qwen3Embedder
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

QS = [("258171", "87", "¿Cada cuánto se sientan a planear qué torres nuevas hay que construir y quién lo hace?"),
      ("258171", "212", "Ese grupo que resuelve las peleas entre las empresas y el operador, ¿quién paga lo que cuesta tenerlo funcionando?")]


def ollama_embed(model, text):
    d = json.dumps({"model": model, "input": [text]}).encode()
    r = urllib.request.Request("http://localhost:11434/api/embed", data=d, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=120) as x:
        return json.loads(x.read())["embeddings"][0]


def trunc(v, d):
    s = v[:d]; n = math.sqrt(sum(a*a for a in s)) or 1.0
    return [a/n for a in s]


def ranking(col, emb, topn=50):
    """Devuelve lista de (id_norma, art_norm) ordenada por similitud."""
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute(f"""SELECT a.id_norma, a.numero FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id
            WHERE f.{col} IS NOT NULL ORDER BY f.{col} <=> %s::vector LIMIT %s""", (str(emb), topn))
        # dedup por artículo conservando primer rank
        seen, out = set(), []
        for x in cur.fetchall():
            key = (x["id_norma"], _normalize_art(str(x["numero"])))
            if key not in seen:
                seen.add(key); out.append(key)
        return out


def rrf(rankings, k=60):
    sc = {}
    for r in rankings:
        for rank, key in enumerate(r, 1):
            sc[key] = sc.get(key, 0) + 1/(k+rank)
    return [kk for kk in sorted(sc, key=lambda x: -sc[x])]


def rank_of(order, gold):
    for i, key in enumerate(order, 1):
        if key == gold:
            return i
    return None


def main():
    e06 = Qwen3Embedder()
    from sentence_transformers import SentenceTransformer
    import os
    bge = SentenceTransformer("BAAI/bge-m3", device=os.environ.get("BGE_DEVICE", "cpu"))
    for nm, ar, q in QS:
        gold = (nm, _normalize_art(ar))
        v06 = e06.embed([q])[0]
        v4 = ollama_embed("qwen3-embedding:4b", q)
        v8 = ollama_embed("qwen3-embedding:8b", q)
        vb = bge.encode([q], normalize_embeddings=True)[0].tolist()
        r06 = ranking("embedding", v06)
        r4 = ranking("embedding_4b", v4)
        r8 = ranking("embedding_8b", v8)
        rb = ranking("embedding_bgem3", vb)
        print(f"\n=== {nm}/{ar} :: {q[:50]} ===")
        for name, r in [("0.6B", r06), ("4B", r4), ("8B", r8), ("bge-m3", rb),
                        ("RRF 4B+bge-m3", rrf([r4, rb])), ("RRF 4B+8B", rrf([r4, r8])),
                        ("RRF 4B+bge-m3+0.6B", rrf([r4, rb, r06]))]:
            pos = rank_of(r, gold)
            print(f"  {name:22s} rank={pos if pos else '>50'}  {'TOP10' if pos and pos<=10 else ''}")


if __name__ == "__main__":
    main()
