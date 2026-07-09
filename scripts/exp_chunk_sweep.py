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


# --- marcadores extendidos (cubre §, N°, romano, ordinal, guion) ---
_MARK2 = re.compile(
    r"(?:^|\n|;)\s*(?:"
    r"[a-zñ]{1,2}|\d{1,2}"           # a. 1.
    r"|\d{1,2}[°º]"                    # 1°
    r"|[IVXLC]{1,4}"                   # romano I. II.
    r"|Primero|Segundo|Tercero|Cuarto|Quinto|Sexto|Séptimo|Octavo|Noveno|Décimo"
    r")[.)\-]\s+"
    r"|§\s*\d"
)
_SENT = re.compile(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÑ0-9])")
HUGE = 3000


def ck_inciso_robust(art):
    t = art["texto"]
    marks = list(_MARK2.finditer(t))
    if len(marks) < 2:
        return [t.strip()]
    pieces = []
    head = t[: marks[0].start()].strip()
    if head:
        pieces.append(head)
    for i, mk in enumerate(marks):
        s = mk.start(); e = marks[i + 1].start() if i + 1 < len(marks) else len(t)
        p = t[s:e].strip()
        if p:
            pieces.append(p)
    return pieces or [t.strip()]


def _split_huge(piece):
    """Parte un fragmento >HUGE por oración, acumulando ~HUGE chars."""
    if len(piece) <= HUGE:
        return [piece]
    sents = _SENT.split(piece)
    out, cur = [], ""
    for s in sents:
        if cur and len(cur) + len(s) > HUGE:
            out.append(cur.strip()); cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur.strip())
    return out or [piece]


def ck_inciso_maxsplit(art):
    out = []
    for p in ck_inciso_robust(art):
        out.extend(_split_huge(p))
    return out


def ck_recursive(art, size=600, seps=("\n\n", "\n", ". ", "; ")):
    """Recursive char split (estándar langchain-like): baja por separadores hasta
    que los trozos caben en `size`. Para prosa larga sin marcadores legales."""
    def rec(text, si):
        text = text.strip()
        if len(text) <= size or si >= len(seps):
            return [text] if text else []
        parts = text.split(seps[si])
        out, cur = [], ""
        for p in parts:
            cand = f"{cur}{seps[si]}{p}" if cur else p
            if len(cand) <= size:
                cur = cand
            else:
                if cur:
                    out.extend(rec(cur, si + 1))
                cur = p
        if cur:
            out.extend(rec(cur, si + 1))
        return out
    return rec(art["texto"], 0) or [art["texto"].strip()]


CHUNKERS = {"whole": ck_whole, "glossary": ck_glossary, "inciso": ck_inciso,
            "slide1000_200": ck_slide1000_200, "slide500_100": ck_slide500_100,
            "inciso_robust": ck_inciso_robust, "inciso_maxsplit": ck_inciso_maxsplit,
            "recursive": ck_recursive}


# ---------- contexto: (art, frag) -> texto a embeber ----------
def ctx_none(art, frag):
    return frag


def ctx_light(art, frag):
    return f"[{art['id_norma']}/{art['numero']}] {frag}"


def ctx_path(art, frag):
    tit = (art.get("titulo") or "").strip()
    p = f"[{art['id_norma']} > {tit} > art {art['numero']}]" if tit else f"[{art['id_norma']} > art {art['numero']}]"
    return f"{p} {frag}"


# ---------- REGLA 4: cross-ref (inyección determinista, sin LLM) ----------
# El QA mostró la patología: un chunk referencia algo que no contiene
# ("conforme al artículo 225", "el Coordinador"). Le devolvemos ese contexto.
# 53.7% de artículos tienen remisión real; 53.8% resuelven en la misma norma.
_HEAD = re.compile(r"^\s*Art[íi]culo\s+[\dºª°]+[^\n]{0,20}", re.I)
_REF = re.compile(r"(?:art[íi]culos?|art\.)\s*(\d{1,3})", re.I)
REF_SNIP = 240   # chars del artículo referenciado que se anexan
MAX_REFS = 2     # cuántas remisiones se anexan como máximo
DEF_SNIP = 200   # chars de la definición inyectada
MAX_DEFS = 2
MIN_DEF_TERM = 10  # término debe ser específico (evita "energía"/"empresa" → 83% chunks)

_ART_IDX: dict = {}   # (id_norma, numero_str) -> texto
_DEF_IDX: dict = {}   # termino_lower -> definicion


def build_indexes(arts):
    """Índice de artículos (para remisiones) y de definiciones de glosario."""
    _ART_IDX.clear(); _DEF_IDX.clear()
    for a in arts:
        _ART_IDX[(a["id_norma"], str(a["numero"]).strip())] = a["texto"]
        if _GLOS.search(a["texto"]):
            for frag in ck_glossary(a)[1:]:          # saltea el header
                if ":" in frag:
                    t, d = frag.split(":", 1)
                    t = t.strip().lower()
                    if 3 <= len(t) <= 60 and t not in _DEF_IDX:
                        _DEF_IDX[t] = d.strip()


def _refs_of(art):
    body = _HEAD.sub("", art["texto"], count=1)       # sin su propio encabezado
    own = re.sub(r"[^0-9]", "", str(art["numero"]))
    out = []
    for r in _REF.findall(body):
        if r == own or r in out:
            continue
        if (art["id_norma"], r) in _ART_IDX:          # resolvible en la misma norma
            out.append(r)
        if len(out) >= MAX_REFS:
            break
    return out


def _xref_adds(art):
    """Snippets de los artículos que este artículo referencia."""
    out = []
    for r in _refs_of(art):
        t = _HEAD.sub("", _ART_IDX[(art["id_norma"], r)], count=1).strip()
        out.append(f"[Ref. art {r}: {t[:REF_SNIP]}]")
    return out


def _def_adds(frag):
    """Definiciones de glosario de los términos que aparecen en el fragmento.

    Solo términos ESPECÍFICOS: >=MIN_DEF_TERM chars y match por palabra completa.
    Sin esto, términos genéricos ("energía", "empresa") disparan en el 83% de los
    chunks y todos los embeddings convergen → retrieval peor, no mejor."""
    low, out = frag.lower(), []
    for term, d in _DEF_IDX.items():
        if len(term) < MIN_DEF_TERM:
            continue
        if re.search(rf"\b{re.escape(term)}\b", low):
            out.append(f"[Def. {term}: {d[:DEF_SNIP]}]")
            if len(out) >= MAX_DEFS:
                break
    return out


def _join(base, adds):
    return base + (" " + " ".join(adds) if adds else "")


def ctx_xref(art, frag):
    """path + texto de los artículos que el chunk referencia."""
    return _join(ctx_path(art, frag), _xref_adds(art))


def ctx_defs(art, frag):
    """path + definición de los términos de glosario que el chunk usa."""
    return _join(ctx_path(art, frag), _def_adds(frag))


def ctx_xref_defs(art, frag):
    """path + remisiones + definiciones (regla 4 completa)."""
    return _join(ctx_path(art, frag), _xref_adds(art) + _def_adds(frag))


CTXS = {"none": ctx_none, "light": ctx_light, "path": ctx_path,
        "xref": ctx_xref, "defs": ctx_defs, "xref_defs": ctx_xref_defs}

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
    # --- ronda 2 (2026-07-07): cobertura de estructura del QA ---
    "inciso_robust+path": ("inciso_robust", "path"),
    "inciso_robust+light": ("inciso_robust", "light"),
    "inciso_maxsplit+path": ("inciso_maxsplit", "path"),
    "recursive+path": ("recursive", "path"),
    "recursive+light": ("recursive", "light"),
    # --- ronda 3 (2026-07-09): REGLA 4 cross-ref, sobre granularidad de producción ---
    "whole+xref": ("whole", "xref"),
    "whole+defs": ("whole", "defs"),
    "whole+xref_defs": ("whole", "xref_defs"),
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
    if ctx_name in ("xref", "defs", "xref_defs") and not _ART_IDX:
        build_indexes(arts)   # índices de remisiones y definiciones (regla 4)
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
