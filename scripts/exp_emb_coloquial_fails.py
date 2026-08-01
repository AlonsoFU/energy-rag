"""¿Algún embedder (de los YA poblados) rankea mejor el gold en las coloquiales que fallan?
Mide rank del gold top-50 para 0.6B / 4B / 8B / bge-m3 + RRF combos. Solo retrieval (sin gen).

Uso: PYTHONPATH=. BGE_DEVICE=cuda venv/bin/python -m scripts.exp_emb_coloquial_fails
"""
import json, urllib.request, math, os
from src.components.embedder import Qwen3Embedder
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

QS = [("258171", "104", "¿Por cuántos años se supone que dura una torre o línea para sacar la cuenta de lo que cuesta?"),
      ("258171", "198", "¿cada cuánto me tienen que mandar la cuenta de la luz?"),
      ("1149788", "2", "quiero poner paneles en el techo de mi casa, ¿hay un tope de tamaño para que entre en este beneficio de inyectar a la red?"),
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
    e06 = Qwen3Embedder()
    from sentence_transformers import SentenceTransformer
    bge = SentenceTransformer("BAAI/bge-m3", device=os.environ.get("BGE_DEVICE", "cpu"))
    print(f"{'caso':14s} {'0.6B':>5s} {'4B':>5s} {'8B':>5s} {'bgeM3':>6s} {'RRF4B+bge':>10s} {'RRF4B+8B':>9s}", flush=True)
    for nm, ar, q in QS:
        g = (nm, _normalize_art(ar))
        r06 = ranking("embedding", e06.embed([q])[0])
        r4 = ranking("embedding_4b", ollama_embed("qwen3-embedding:4b", q))
        r8 = ranking("embedding_8b", ollama_embed("qwen3-embedding:8b", q))
        rb = ranking("embedding_bgem3", bge.encode([q], normalize_embeddings=True)[0].tolist())
        fmt = lambda r: (str(r) if r else ">50")
        print(f"{nm+'/'+ar:14s} {fmt(rank_of(r06,g)):>5s} {fmt(rank_of(r4,g)):>5s} {fmt(rank_of(r8,g)):>5s} "
              f"{fmt(rank_of(rb,g)):>6s} {fmt(rank_of(rrf([r4,rb]),g)):>10s} {fmt(rank_of(rrf([r4,r8]),g)):>9s}", flush=True)


if __name__ == "__main__":
    main()
