"""EXP autoridad — ¿el boost por jerarquía normativa mueve cita_ok?

Barre authority_rank_boost (β) sobre la pipeline de producción real
(AdaptiveRetriever → generate_answer) y mide cita_ok por set. Carga los modelos
UNA vez; solo cambia cfg.settings.authority_rank_boost entre corridas.

β=0.0 = baseline (prod actual). LEGAL(3)→×(1+β), DECRETO(2)→×1, RESOLUCIÓN(1)→×(1-β).

Uso: HF_HUB_OFFLINE=1 ./venv-gpu/bin/python -m scripts.exp_authority \
        coloquial:data/eval/queries_coloquial_v2.jsonl dev:data/eval/queries_independent.jsonl -- 0.0 0.1 0.2
"""
import json, sys
from pathlib import Path
from collections import defaultdict
from src.components.embedder import Qwen3Embedder
from src.components.reranker import get_reranker
from src.components.vectorstore import PostgresStore
from src.components.llm import get_llm_provider
from src.pipelines.retrieve import SimpleRetriever, ComplexRetriever, AdaptiveRetriever
from src.routing.adaptive import AdaptiveRouter
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT
from src.core import config as cfg

OUT = Path("data/eval/results/authority"); OUT.mkdir(parents=True, exist_ok=True)


def _golds(q):
    out = {(str(q["expected_norma"]), _normalize_art(str(q["expected_articulo"])))}
    for g in q.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _ok(txt, golds):
    cits = extract_citations(txt)
    return (any((str(n), _normalize_art(str(a))) in golds for n, a in cits)
            and REFUSAL_TEXT.lower() not in txt.lower())


def main():
    args = sys.argv[1:]
    i = args.index("--")
    sets = [s.split(":", 1) for s in args[:i]]
    betas = [float(b) for b in args[i + 1:]]
    pool = cfg.settings.retrieval_pool_depth
    e = Qwen3Embedder(); r = get_reranker(); store = PostgresStore(); llm = get_llm_provider()
    router = AdaptiveRouter(); router.train_default()
    simple = SimpleRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    complejo = ComplexRetriever(store, e, r, top_bm25=pool, top_vector=pool, llm=llm)
    adaptive = AdaptiveRetriever(simple, complejo, router)

    ckf = OUT / "sweep.json"
    done = json.loads(ckf.read_text()) if ckf.exists() else {}
    print(f"betas={betas} sets={[s[0] for s in sets]}", flush=True)
    for name, path in sets:
        rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
        rows = [q for q in rows if q.get("expected_norma")]
        for beta in betas:
            key = f"{name}@{beta}"
            rec = done.get(key, {})
            cfg.settings.authority_rank_boost = beta
            nok = sum(rec.values()) if rec else 0
            for j, q in enumerate(rows):
                qk = q["query"]
                if qk in rec:
                    continue
                golds = _golds(q)
                try:
                    _, docs = adaptive.retrieve(qk, top_k=5)
                    txt = generate_answer(qk, docs, llm=llm)["text"]
                    ok = int(_ok(txt, golds))
                except Exception as ex:
                    print(f"  {key} {j+1} FAIL {str(ex)[:40]}", flush=True); ok = 0
                rec[qk] = ok; nok += ok
                done[key] = rec; ckf.write_text(json.dumps(done, ensure_ascii=False))
            cfg.settings.authority_rank_boost = 0.0
            print(f"  {key:20s} cita_ok={sum(rec.values())}/{len(rows)}", flush=True)
    print("\n=== RESUMEN cita_ok ===", flush=True)
    for name, path in sets:
        n = len([1 for l in Path(path).read_text().splitlines() if l.strip() and json.loads(l).get("expected_norma")])
        line = f"  {name:12s}(n={n})"
        for beta in betas:
            rec = done.get(f"{name}@{beta}", {})
            line += f"  β{beta}={sum(rec.values())}"
        print(line, flush=True)


if __name__ == "__main__":
    main()
