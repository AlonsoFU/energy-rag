"""Barrido de estrategias de CHUNKING (reglas 1-4 legal-RAG), NO-destructivo.

Para cada estrategia (chunker × contexto) re-chunkea en MEMORIA desde articulos.texto,
embebe con 4B (ollama, MRL-1024 = producción), mide gold∈top5/top10 sobre coloquial+dev.
Cero escritura a DB. Checkpoint por estrategia. El screen MIENTE → confirmar el ganador
end-to-end antes de adoptar.

Uso: HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.exp_chunk_sweep [estrategia ...]
"""
import json, sys, os, re, time, urllib.request
from pathlib import Path
import numpy as np
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.pipelines.grounding import _normalize_art

OUTDIR = Path("data/eval/results/chunk_sweep")
SETS = [("coloquial", "data/eval/queries_coloquial_v2.jsonl"),
        ("dev", "data/eval/queries_independent.jsonl")]
EMB_MODEL = "qwen3-embedding:4b"
MRL = 1024  # producción

# --- marcadores de subdivisión legal (glosario e incisos) ---
_GLOS = re.compile(r"se\s+entender[áa]\s+por\s*:", re.IGNORECASE)
_MARK = re.compile(r"(?:^|\n|;)\s*(?:[a-zñ]{1,2}|\d{1,2})[.)]\s+")


# ---------- chunkers: art(dict) -> list[str] (fragmentos crudos) ----------
def ck_whole(art):
    return [art["texto"].strip()]


def ck_glossary(art):
    t = art["texto"]
    m = _GLOS.search(t)
    if not m:
        return [t.strip()]
    header = t[: m.end()].strip()
    body = t[m.end():]
    marks = list(_MARK.finditer(body))
    defs = []
    for i, mk in enumerate(marks):
        s = mk.end(); e = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        chunk = body[s:e].strip().rstrip(";").strip()
        if ":" in chunk:
            term, d = chunk.split(":", 1)
            if term.strip() and d.strip() and len(term.strip()) <= 90:
                defs.append(f"{term.strip()}: {d.strip()}")
    if len(defs) < 4:
        return [t.strip()]
    return [header] + defs


def ck_inciso(art):
    t = art["texto"]
    marks = list(_MARK.finditer(t))
    if len(marks) < 2:
        return [t.strip()]
    pieces, prev = [], 0
    head = t[: marks[0].start()].strip()
    if head:
        pieces.append(head)
    for i, mk in enumerate(marks):
        s = mk.start(); e = marks[i + 1].start() if i + 1 < len(marks) else len(t)
        p = t[s:e].strip()
        if p:
            pieces.append(p)
    return pieces or [t.strip()]


def _slide(t, size, overlap):
    t = t.strip()
    if len(t) <= size:
        return [t]
    out, i = [], 0
    while i < len(t):
        out.append(t[i:i + size])
        i += size - overlap
    return out


def ck_slide1000_200(art):
    return _slide(art["texto"], 1000, 200)


def ck_slide500_100(art):
    return _slide(art["texto"], 500, 100)


CHUNKERS = {"whole": ck_whole, "glossary": ck_glossary, "inciso": ck_inciso,
            "slide1000_200": ck_slide1000_200, "slide500_100": ck_slide500_100}


# ---------- contexto: (art, frag) -> texto a embeber ----------
def ctx_none(art, frag):
    return frag


def ctx_light(art, frag):
    return f"[{art['id_norma']}/{art['numero']}] {frag}"


def ctx_path(art, frag):
    tit = (art.get("titulo") or "").strip()
    p = f"[{art['id_norma']} > {tit} > art {art['numero']}]" if tit else f"[{art['id_norma']} > art {art['numero']}]"
    return f"{p} {frag}"


CTXS = {"none": ctx_none, "light": ctx_light, "path": ctx_path}

# estrategia -> (chunker, ctx). 'asis' es especial (lee fragmentos de la DB).
STRATS = {
    "asis": None,
    "whole+light": ("whole", "light"),
    "whole+path": ("whole", "path"),
    "glossary+light": ("glossary", "light"),
    "glossary+path": ("glossary", "path"),
    "inciso+light": ("inciso", "light"),
    "inciso+path": ("inciso", "path"),
    "slide1000_200+light": ("slide1000_200", "light"),
    "slide1000_200+path": ("slide1000_200", "path"),
    "slide500_100+light": ("slide500_100", "light"),
    "whole+none": ("whole", "none"),
    "glossary+none": ("glossary", "none"),
}


def load_articulos():
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, id_norma, numero, titulo, texto FROM articulos WHERE texto IS NOT NULL AND texto <> ''")
        return cur.fetchall()


def build_corpus(strat, arts):
    """-> (keys, texts). keys=[(id_norma, norm_numero)] alineado con texts."""
    if strat == "asis":
        with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT a.id_norma, a.numero, f.contextual_text, f.text
                           FROM fragmentos f JOIN articulos a ON a.id=f.articulo_id""")
            rows = cur.fetchall()
        keys = [(r["id_norma"], _normalize_art(str(r["numero"]))) for r in rows]
        texts = [(r["contextual_text"] or r["text"]) for r in rows]
        return keys, texts
    ck_name, ctx_name = STRATS[strat]
    ck, ctx = CHUNKERS[ck_name], CTXS[ctx_name]
    keys, texts = [], []
    for a in arts:
        k = (a["id_norma"], _normalize_art(str(a["numero"])))
        for frag in ck(a):
            if not frag.strip():
                continue
            keys.append(k)
            texts.append(ctx(a, frag))
    return keys, texts


def load_queries():
    out = []
    for s, p in SETS:
        for l in Path(p).read_text().splitlines():
            if not l.strip():
                continue
            q = json.loads(l)
            if q.get("expected_norma") is None:
                continue
            g = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
            for x in q.get("also_gold") or []:
                n, a = str(x).split("/", 1); g.add((n, _normalize_art(a)))
            out.append((s, q["query"], g))
    return out


def ollama_embed(texts, bs=16):
    out = []
    for i in range(0, len(texts), bs):
        d = json.dumps({"model": EMB_MODEL, "input": texts[i:i + bs]}).encode()
        r = urllib.request.Request("http://localhost:11434/api/embed", data=d,
                                   headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=600) as x:
            out.extend(json.loads(x.read())["embeddings"])
    v = np.array(out, dtype=np.float32)[:, :MRL]
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def gold_rank(sims, keys, gold, topn=50):
    order = np.argsort(-sims)[:topn]
    seen, rank = set(), 0
    for idx in order:
        k = keys[idx]
        if k in seen:
            continue
        seen.add(k); rank += 1
        if k in gold:
            return rank
    return None


def main():
    names = sys.argv[1:] or list(STRATS.keys())
    OUTDIR.mkdir(parents=True, exist_ok=True)
    arts = load_articulos()
    queries = load_queries()
    qtexts = [q for _, q, _ in queries]
    print(f"articulos={len(arts)} queries={len(queries)} strats={names}", flush=True)
    qv = ollama_embed(qtexts)
    rj = OUTDIR / "result.json"
    res = json.loads(rj.read_text()) if rj.exists() else {}
    for nm in names:
        if nm in res:
            print(f"SKIP {nm}", flush=True); continue
        t0 = time.time()
        try:
            keys, texts = build_corpus(nm, arts)
            dv = ollama_embed(texts)
            agg = {}
            for (s, _, gold), qrow in zip(queries, qv):
                r = gold_rank(dv @ qrow, keys, gold)
                a = agg.setdefault(s, {"n": 0, "t5": 0, "t10": 0})
                a["n"] += 1; a["t5"] += (r is not None and r <= 5); a["t10"] += (r is not None and r <= 10)
            res[nm] = {"agg": agg, "n_frags": len(texts), "secs": round(time.time() - t0)}
            rj.write_text(json.dumps(res, ensure_ascii=False, indent=2))
            print(f"{nm}: frags={len(texts)} " + " ".join(f"{s} t5={a['t5']}/{a['n']} t10={a['t10']}" for s, a in agg.items()) + f"  ({res[nm]['secs']}s)", flush=True)
        except Exception as ex:
            print(f"FAIL {nm}: {str(ex)[:160]}", flush=True); continue
    print("\n=== CHUNK SWEEP (gold∈topN, embed 4b-1024) ===", flush=True)
    print(f"{'estrategia':24s} {'frags':>6s} {'cx_t5':>6s} {'cx_t10':>7s} {'dev_t5':>7s} {'dev_t10':>8s}", flush=True)
    for nm in names:
        if nm not in res: continue
        a = res[nm]["agg"]; cx = a.get("coloquial", {}); dv = a.get("dev", {})
        print(f"{nm:24s} {res[nm].get('n_frags',0):>6d} {cx.get('t5',0):>6d} {cx.get('t10',0):>7d} {dv.get('t5',0):>7d} {dv.get('t10',0):>8d}", flush=True)


if __name__ == "__main__":
    main()
