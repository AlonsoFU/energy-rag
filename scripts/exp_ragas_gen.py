"""RAGAS paso A — genera answers sobre los pools cacheados y arma el dataset.

Reusa los pools YA cacheados en gen_bakeoff (retrieval hecho, no se recalcula).
Solo genera el answer con el generador elegido y adjunta el texto gold como
referencia. Sale un .jsonl que el paso B (venv ragas) consume.

Necesita src + Ollama/Claude → corre en venv-gpu:
  HF_HUB_OFFLINE=1 GEN_MODEL=ollama/qwen3:30b-a3b \
    ./venv-gpu/bin/python -m scripts.exp_ragas_gen coloquial dev

Salida: data/eval/results/ragas/{set}__{modelo}.jsonl
Campos por línea: set, question, answer, retrieved_contexts, reference,
                  reference_contexts, cita_ok, golds.
"""
import json, os, sys
from pathlib import Path
from psycopg.rows import dict_row
from src.storage.connection import with_connection
from src.components.llm import get_llm_provider
from src.pipelines.generate import generate_answer
from src.pipelines.grounding import _normalize_art
from scripts.exp_gen_bakeoff import _ok, _golds

GENM = os.environ.get("GEN_MODEL", "ollama/qwen3:30b-a3b")
GB = Path("data/eval/results/gen_bakeoff/result.json")
OUT = Path("data/eval/results/ragas"); OUT.mkdir(parents=True, exist_ok=True)


def gold_texts():
    """(id_norma, num_norm) -> articulos.texto  (referencia gold)."""
    idx = {}
    with with_connection() as c, c.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id_norma, numero, texto FROM articulos")
        for r in cur.fetchall():
            k = (str(r["id_norma"]), _normalize_art(str(r["numero"])))
            idx[k] = r["texto"] or ""
    return idx


def main():
    sets = sys.argv[1:] or ["coloquial", "dev"]
    det = json.loads(GB.read_text())["detail"]
    gtx = gold_texts()
    llm = get_llm_provider()
    tag = GENM.split("/")[-1].replace(":", "-")
    for s in sets:
        rows = [it for it in det if it["set"] == s]
        of = OUT / f"{s}__{tag}.jsonl"
        done = {}
        if of.exists():
            for l in of.open():
                if l.strip():
                    r = json.loads(l); done[r["question"]] = r
        print(f"[{s}] {len(rows)} queries · gen={GENM} · ya={len(done)}", flush=True)
        with of.open("w") as fh:
            n_ok = 0
            for i, it in enumerate(rows):
                q = it["q"]
                if q in done:
                    rec = done[q]
                else:
                    docs = it["docs"]
                    golds = set(tuple(g) for g in it["golds"])
                    # golds del item vienen como [id_norma, art]; normalizar art
                    gset = {(str(n), _normalize_art(str(a))) for n, a in golds}
                    try:
                        res = generate_answer(q, docs, llm=llm, model=GENM)
                        ans = res["text"]; ok = int(_ok(res, gset))
                    except Exception as ex:
                        print(f"  {i+1} GEN-FAIL: {str(ex)[:60]}", flush=True)
                        ans = ""; ok = 0
                    contexts = [d.get("contextual_text") or d.get("text") or "" for d in docs]
                    ref_ctx = [gtx.get(g, "") for g in gset if gtx.get(g)]
                    rec = {
                        "set": s, "question": q, "answer": ans,
                        "retrieved_contexts": contexts,
                        "reference": "\n\n".join(ref_ctx),
                        "reference_contexts": ref_ctx,
                        "cita_ok": ok,
                        "golds": sorted(list(gset)),
                    }
                n_ok += rec["cita_ok"]
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n"); fh.flush()
                print(f"  {i+1}/{len(rows)} cita_ok={rec['cita_ok']} acum={n_ok}", flush=True)
        print(f"[{s}] listo → {of}  cita_ok={n_ok}/{len(rows)}", flush=True)


if __name__ == "__main__":
    main()
