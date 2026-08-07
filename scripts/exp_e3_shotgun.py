"""E3: auditar el EFECTO ESCOPETA en cita_ok.

Hipotesis: `cita_ok` marca True si CUALQUIER cita del texto pega con el gold. Una respuesta que
dispara muchas citas (medido: 28, mayoria duplicadas, en "que es Superintendencia") puede acertar
por VOLUMEN y no por precision. Si una porcion de los ~252 aciertos son asi, la metrica infla.

Mide, por query, sobre la config VIGENTE (glossary_inject ON, ctx 32768, num_predict 2000):
  - n_cits_total / n_cits_unicas  (cuantas dispara)
  - hit                           (cita_ok actual: ALGUNA pega)
  - hit_first                     (la PRIMERA cita pega)  <- metrica de precision
  - rank_hit                      (en que posicion aparece la cita correcta)
  - precision                     (cits unicas correctas / cits unicas)
Y PERSISTE EL TEXTO de cada respuesta (`text`) — ningun eval anterior lo guardo, por eso no se
pudo auditar retroactivamente.

No es un experimento A/B: es una foto de la config actual. No lleva McNemar.

Uso: BGE_DEVICE=cuda PYTHONPATH=. venv/bin/python -m scripts.exp_e3_shotgun
"""
import json, subprocess, time
from pathlib import Path
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

MODEL = "ollama/qwen3:30b-a3b"
SET = "data/eval/queries_balanced_v2_clean.jsonl"
OUTDIR = Path("data/eval/results/e3_shotgun")


def golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def main():
    rows = [json.loads(l) for l in Path(SET).read_text().splitlines() if l.strip()]
    rows = [q for q in rows if q.get("category") == "in_domain"]
    subprocess.run(["ollama", "stop", "qwen3-embedding:8b"], capture_output=True)
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg.settings.embed_4b_dense = True; cfg.settings.embed_4b_dim = 1024; cfg.settings.alias_union = True
    pool = cfg.settings.retrieval_pool_depth
    retr = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)

    prev = {}
    rp = OUTDIR / "result.json"
    if rp.exists():
        try:
            for c in json.load(open(rp))["detail"]:
                if c.get("hit") is not None: prev[c["query"]] = c
            print(f"[RESUME] {len(prev)} ya medidas", flush=True)
        except Exception as ex:
            print(f"[RESUME] fallo: {type(ex).__name__}", flush=True)

    print(f"=== E3: midiendo {len(rows)}q (config vigente) ===", flush=True)
    out = []
    for i, q in enumerate(rows):
        if q["query"] in prev:
            out.append(prev[q["query"]]); continue
        gs = golds(q)
        rec = {"query": q["query"], "gold": sorted(f"{n}/{a}" for n, a in gs)}
        docs = retr.retrieve(q["query"], top_k=10)
        txt, err = "", False
        for a in (1, 2, 3):
            try:
                txt = generate_answer(q["query"], docs, llm=llm, model=MODEL)["text"]; break
            except Exception as ex:
                print(f"    ! fail '{q['query'][:24]}' {type(ex).__name__}", flush=True)
                time.sleep(3); err = (a == 3)
        cits = [(str(n), _normalize_art(str(a))) for n, a in extract_citations(txt)]
        uniq = list(dict.fromkeys(cits))
        good = [c for c in uniq if c in gs]
        rank = next((j for j, c in enumerate(cits) if c in gs), None)
        rec.update({
            "err": err,
            "refusal": REFUSAL_TEXT.lower() in txt.lower(),
            "n_cits": len(cits), "n_uniq": len(uniq),
            "hit": bool(good) and REFUSAL_TEXT.lower() not in txt.lower(),
            "hit_first": bool(cits) and cits[0] in gs,
            "rank_hit": rank,
            "precision": (len(good) / len(uniq)) if uniq else 0.0,
            "cits": [f"{n}/{a}" for n, a in uniq],
            "text": txt,          # <- lo que ningun eval anterior guardo
        })
        out.append(rec)
        if (i + 1) % 5 == 0:
            (OUTDIR / "result.json").write_text(json.dumps({"detail": out}, ensure_ascii=False, default=str))
            print(f"  {i+1}/{len(rows)}", flush=True)
    (OUTDIR / "result.json").write_text(json.dumps({"detail": out}, ensure_ascii=False, default=str))

    val = [x for x in out if not x["err"]]
    hits = [x for x in val if x["hit"]]
    print(f"\n=== E3 EFECTO ESCOPETA ({len(val)} queries validas) ===", flush=True)
    print(f"  cita_ok (ALGUNA pega):   {len(hits)}/{len(val)}", flush=True)
    print(f"  hit_first (la 1a pega):  {sum(x['hit_first'] for x in val)}/{len(val)}", flush=True)
    if val:
        print(f"  citas por respuesta:     media {sum(x['n_cits'] for x in val)/len(val):.1f}  "
              f"unicas {sum(x['n_uniq'] for x in val)/len(val):.1f}  max {max(x['n_cits'] for x in val)}", flush=True)
    if hits:
        print(f"  precision media EN HITS: {sum(x['precision'] for x in hits)/len(hits):.2f}", flush=True)
    for thr in (3, 5, 10):
        n = sum(1 for x in hits if x["n_uniq"] > thr)
        print(f"  hits con >{thr} citas unicas: {n}/{len(hits)}  ({100*n/max(1,len(hits)):.0f}%)  <- sospechosos de VOLUMEN", flush=True)
    susp = sorted([x for x in hits if x["n_uniq"] > 5], key=lambda x: -x["n_uniq"])[:12]
    if susp:
        print("\n  TOP sospechosos (hit con muchas citas):", flush=True)
        for x in susp:
            print(f"    {x['n_uniq']:3d} uniq (rank_hit={x['rank_hit']}) prec={x['precision']:.2f}  {x['query'][:48]}", flush=True)


if __name__ == "__main__":
    main()
