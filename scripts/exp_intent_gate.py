"""B2.2 — GATE binario definicion/no-definicion (lo que le falta a glossary_lookup).

`glossary_lookup` (exp #42b) extrae bien el termino, pero NO decide si corresponde
inyectar: sobre queries operativas dispara 20/51 (complex_v3) y 10/24 (holdout) —
"Cliente", "Ley", "Comision", "Coordinador" son terminos de glosario que aparecen en
cualquier pregunta. Sin gate, el diccionario contamina lo operativo.

El probe (#42) mostro que el coseno agrupa por TOPICO, asi que el centroide es debil.
Aqui se comparan tres gates sobre los MISMOS embeddings:

  centroide      coseno contra el centroide de cada intencion (baseline del probe)
  logreg         regresion logistica binaria — aprende que dimensiones separan la
                 INTENCION e ignora las del topico. Es un clasificador de verdad.
  regex          `_is_definition_query`, el mecanismo actual (referencia)

Etiquetas: positivos = queries de definicion (fraseos_v1 + set primario). Negativos =
operativas (complex_v3 completo + holdout excluyendo las que el regex marca como
definicion, para no meter positivos disfrazados en el set negativo).
⚠️ La etiqueta negativa es APROXIMADA (heredada del set, no revisada una por una).

  PYTHONPATH=. venv/bin/python -m scripts.exp_intent_gate
"""
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from src.pipelines.retrieve import _embed_4b_query, _is_definition_query

DIM = 1024
OUT = Path("data/eval/results/intent_gate")
CACHE = OUT / "emb_cache.json"


def cargar(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    pos = [q["query"] for q in cargar("data/eval/queries_fraseos_v1.jsonl")]
    prim = [q["query"] for q in cargar("data/eval/queries_balanced_v2_clean.jsonl")
            if q.get("category") == "in_domain"]
    pos += prim
    neg = [q["query"] for q in cargar("data/eval/queries_complex_v3.jsonl")]
    neg += [q["query"] for q in cargar("data/eval/queries_holdout.jsonl")
            if not _is_definition_query(q["query"])]
    # ejemplos escritos a mano: son el material de entrenamiento honesto
    ej = cargar("data/intents/ejemplos_v1.jsonl")
    pos += [e["text"] for e in ej if e["intent"] == "definicion"]
    neg += [e["text"] for e in ej if e["intent"] != "definicion"]

    pos, neg = list(dict.fromkeys(pos)), list(dict.fromkeys(neg))
    textos = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg))
    print(f"positivos(definicion)={len(pos)}  negativos(operativa)={len(neg)}", flush=True)

    faltan = [t for t in textos if t not in cache]
    print(f"embebiendo {len(faltan)} (cache {len(cache)})", flush=True)
    for i, t in enumerate(faltan):
        v = _embed_4b_query(t)
        if not v:
            raise RuntimeError(f"embedding vacio: {t!r}")
        cache[t] = v[:DIM]
        if (i + 1) % 50 == 0:
            CACHE.write_text(json.dumps(cache))
            print(f"  {i+1}/{len(faltan)}", flush=True)
    CACHE.write_text(json.dumps(cache))

    X = np.array([cache[t] for t in textos], dtype=np.float32)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    def report(nombre, pred):
        tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"\n-- {nombre}", flush=True)
        print(f"   recall(dispara donde debe)   {rec:.3f}  ({tp}/{tp+fn})", flush=True)
        print(f"   precision(no contamina)      {prec:.3f}  ({tp}/{tp+fp})   FP={fp}/{fp+tn}", flush=True)
        print(f"   F1 {f1:.3f}", flush=True)
        return {"recall": rec, "precision": prec, "f1": f1, "fp": fp, "fn": fn}

    res = {}
    res["regex"] = report("regex `_is_definition_query` (actual)",
                          np.array([1 if _is_definition_query(t) else 0 for t in textos]))

    cpos = X[y == 1].mean(axis=0); cneg = X[y == 0].mean(axis=0)
    cpos /= np.linalg.norm(cpos); cneg /= np.linalg.norm(cneg)
    res["centroide"] = report("centroide (coseno pos vs neg)",
                              (X @ cpos > X @ cneg).astype(int))

    clf = LogisticRegression(max_iter=2000, C=1.0, class_weight="balanced")
    pred = cross_val_predict(clf, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0))
    res["logreg_cv5"] = report("logreg (5-fold CV, sin ver su propio ejemplo)", pred)

    (OUT / "gate.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\nescrito {OUT}/gate.json", flush=True)
    print("\n⚠️ la etiqueta NEGATIVA es aproximada (heredada del set, no revisada 1x1).", flush=True)


if __name__ == "__main__":
    main()
