"""SMALL-TO-BIG (parent document retrieval / auto-merging) — end-to-end cita_ok.

Hipótesis (estándar de la industria): buscar y responder tienen objetivos OPUESTOS.
  - buscar quiere chunks CHICOS (precisos)   → inciso ganó el screen (+10 dev)
  - responder quiere contexto GRANDE (citable) → inciso perdió el e2e (cx -4)
Separarlos: se indexa chico, se le entrega al LLM el ARTÍCULO COMPLETO (el "padre").

Reusa los pools YA cacheados por exp_chunk_e2e.py (retrieval hecho, no se recalcula).
Solo cambia QUÉ TEXTO se le sirve al generador.

Modos:
  asis_chunk    baseline actual: chunks de producción tal cual (ya medido: cx31/dev36)
  asis_big      pool de producción → artículos padre completos   (aísla el cambio de SERVIR)
  inciso_big    pool inciso → artículos padre completos          (la hipótesis)
  inciso_big_ctx  igual + el contexto LLM del artículo antepuesto

Uso: HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.exp_small_to_big <set.jsonl> [modo ...]
"""
import json, sys, os
from pathlib import Path
from src.storage.connection import with_connection
from psycopg.rows import dict_row
from src.components.llm import get_llm_provider
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import _normalize_art
from scripts.exp_gen_bakeoff import _ok, _golds

GENM = "ollama/" + os.environ.get("GEN_MODEL", "qwen3:30b-a3b")
OUT = Path("data/eval/results/small_to_big"); OUT.mkdir(parents=True, exist_ok=True)
POOLS = Path("data/eval/results/chunk_e2e")
MAX_ART_CHARS = int(os.environ.get("MAX_ART_CHARS", "4000"))  # cap: art 225 tiene 41037
MAX_PARENTS = int(os.environ.get("MAX_PARENTS", "10"))
MODES = ["asis_big", "inciso_big", "inciso_big_ctx"]


def load_articles():
    """(id_norma, num_norm) -> {'texto', 'ctx'}  ctx = frase de contexto del LLM."""
    idx = {}
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, id_norma, numero, texto FROM articulos")
        rows = cur.fetchall()
        byid = {}
        for r in rows:
            k = (str(r["id_norma"]), _normalize_art(str(r["numero"])))
            idx[k] = {"texto": r["texto"] or "", "ctx": ""}
            byid[r["id"]] = k
        # contexto LLM: prefijo de contextual_text antes del "\n\n" del primer fragmento
        cur.execute("""SELECT DISTINCT ON (articulo_id) articulo_id, contextual_text, text
                       FROM fragmentos ORDER BY articulo_id, chunk_index""")
        for r in cur.fetchall():
            k = byid.get(r["articulo_id"])
            ct, tx = r["contextual_text"] or "", r["text"] or ""
            if k and ct and ct != tx:
                idx[k]["ctx"] = ct.split("\n\n", 1)[0].strip() if "\n\n" in ct else ""
    return idx


def parents(docs, arts, with_ctx=False):
    """Chunks recuperados (en orden) -> artículos padre DISTINTOS (auto-merging)."""
    out, seen, trunc = [], set(), 0
    for d in docs:
        k = (str(d.get("id_norma")), _normalize_art(str(d.get("articulo_numero"))))
        if k in seen or k not in arts:
            continue
        seen.add(k)
        t = arts[k]["texto"]
        if len(t) > MAX_ART_CHARS:
            t = t[:MAX_ART_CHARS]; trunc += 1
        if with_ctx and arts[k]["ctx"]:
            t = f"{arts[k]['ctx']}\n\n{t}"
        out.append({"id_norma": k[0], "articulo_numero": d.get("articulo_numero"),
                    "articulo_text": t, "text": t, "contextual_text": t})
        if len(out) >= MAX_PARENTS:
            break
    return out, trunc


def main():
    setf = sys.argv[1]
    modes = sys.argv[2:] or MODES
    stem = Path(setf).stem
    pf = POOLS / f"{stem}__pools.json"
    if not pf.exists():
        sys.exit(f"faltan pools cacheados: {pf}")
    cache = json.loads(pf.read_text())
    rows = [json.loads(l) for l in open(setf) if l.strip()]
    rows = [q for q in rows if q.get("expected_norma")]
    arts = load_articles()
    llm = get_llm_provider()
    # MAX_PARENTS en el nombre: la variante de 5 padres NO debe pisar la de 10
    tag = "" if MAX_PARENTS == 10 else f"__p{MAX_PARENTS}"
    ck = OUT / f"{stem}__{GENM.split('/')[-1].replace(':','-')}{tag}.json"
    done = json.loads(ck.read_text()) if ck.exists() else {}
    print(f"{stem}: {len(rows)} queries · modos={modes} · cap={MAX_ART_CHARS}c/art, max {MAX_PARENTS} padres", flush=True)
    ntr = 0
    for i, q in enumerate(rows):
        key = q["query"]
        if key not in cache:
            continue
        golds = set(_golds(q))
        rec = done.get(key, {})
        for mode in modes:
            if mode in rec:
                continue
            src = "inciso" if mode.startswith("inciso") else "asis"
            docs, tr = parents(cache[key][src], arts, with_ctx=mode.endswith("_ctx"))
            ntr += tr
            try:
                rec[mode] = int(_ok(generate_answer(key, docs, llm=llm, model=GENM), golds))
            except Exception as ex:
                print(f"  {i+1} GEN-FAIL {mode}: {str(ex)[:50]}", flush=True); rec[mode] = 0
        done[key] = rec
        ck.write_text(json.dumps(done, ensure_ascii=False))
        tot = {m: sum(v.get(m, 0) for v in done.values()) for m in modes}
        print(f"  {i+1}/{len(rows)} {rec} | acum {tot}", flush=True)
    print(f"\n=== SMALL-TO-BIG · {stem} (n={len(done)}) ===", flush=True)
    for m in modes:
        print(f"  {m:16s} cita_ok = {sum(v.get(m,0) for v in done.values())}/{len(done)}", flush=True)
    print(f"  (artículos truncados a {MAX_ART_CHARS}c: {ntr})", flush=True)
    print("  baseline asis_chunk (ya medido): coloquial 31/39 · dev 36/44", flush=True)


if __name__ == "__main__":
    main()
