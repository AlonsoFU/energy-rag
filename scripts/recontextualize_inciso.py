"""REMATCH JUSTO — quita el confound del sweep de chunking.

El sweep comparó:
    asis   = chunking grueso + contexto RICO (escrito por LLM, Contextual Retrieval)
    inciso = chunking fino   + contexto POBRE (prefijo "[norma > art N]")
...y aun con el handicap, inciso ganó el screen (+10 dev). Este script le da a inciso
el MISMO tratamiento que a producción: un LLM escribe 1-2 frases del rol del fragmento.

Escribe en fragmentos_inciso.contextual_text y re-embebe embedding_4b_1024.
Resumible: solo procesa los que aún tienen el prefijo "[".

Uso: HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.recontextualize_inciso [--limit N] [--dry-run]
"""
import argparse, json, os, sys, time, urllib.request
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.components.contextual import ContextualEnricher

OLL = "http://localhost:11434"
EMB_MODEL = "qwen3-embedding:4b"
MRL = 1024
# LOCAL por defecto: el default de config (llm_haiku=claude-haiku) son 7141 llamadas PAGADAS.
# CAVEAT: el contextual_text de producción pudo generarse con otro modelo → el rematch
# no es 100% apples-to-apples, pero sí quita el handicap del prefijo tonto.
CTX_MODEL = os.environ.get("CTX_MODEL", "ollama/phi4:14b")


def emb(texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        d = json.dumps({"model": EMB_MODEL, "input": texts[i:i + bs]}).encode()
        r = urllib.request.Request(f"{OLL}/api/embed", data=d,
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=600) as x:
            out.extend(json.loads(x.read())["embeddings"])
    res = []
    for v in out:
        v = v[:MRL]
        n = sum(c * c for c in v) ** 0.5 or 1.0
        res.append([c / n for c in v])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", type=int, default=32)
    a = ap.parse_args()

    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT f.id, f.text, f.numero AS art_num, f.id_norma,
                              n.tipo, n.numero AS norma_numero, n.titulo AS norma_titulo
                       FROM fragmentos_inciso f
                       JOIN normas n ON n.id_norma = f.id_norma
                       WHERE f.contextual_text LIKE '[%'
                       ORDER BY f.id""")
        rows = cur.fetchall()
    if a.limit:
        rows = rows[:a.limit]
    print(f"fragmentos a recontextualizar: {len(rows)}", flush=True)
    if a.dry_run:
        for r in rows[:3]:
            print(f"  id={r['id']} art={r['art_num']} text={r['text'][:70]!r}")
        return

    enr = ContextualEnricher(model=CTX_MODEL)
    print(f"modelo de contexto: {CTX_MODEL}", flush=True)
    t0, buf, nfail = time.time(), [], 0
    for i, r in enumerate(rows, 1):
        titulo = f"{r['tipo']} N° {r['norma_numero']} - {r['norma_titulo']}"
        try:
            ctx = enr.enrich(titulo, str(r["art_num"]), r["text"])
            new = f"{ctx}\n\n{r['text']}"
        except Exception as ex:
            nfail += 1
            new = r["text"]                     # degrada: al menos sin el prefijo tonto
            print(f"  {i} ENRICH-FAIL {str(ex)[:50]}", flush=True)
        buf.append((r["id"], new))
        if len(buf) >= a.batch or i == len(rows):
            vecs = emb([t for _, t in buf])
            with with_connection() as c, c.cursor() as cur:
                for (fid, txt), v in zip(buf, vecs):
                    cur.execute("UPDATE fragmentos_inciso SET contextual_text=%s, "
                                "embedding_4b_1024=%s, tsv=to_tsvector('spanish',%s) "
                                "WHERE id=%s", (txt, str(v), txt, fid))
                c.commit()
            el = time.time() - t0
            print(f"  {i}/{len(rows)}  {el:.0f}s  eta {el/i*(len(rows)-i)/60:.0f}min  fails={nfail}", flush=True)
            buf = []
    print(f"listo en {(time.time()-t0)/60:.0f}min, fails={nfail}", flush=True)


if __name__ == "__main__":
    main()
