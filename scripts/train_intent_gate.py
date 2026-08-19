"""Entrena el GATE binario definicion/no-definicion y guarda los coeficientes.

Regresion logistica sobre embeddings qwen3-embedding:4b (MRL-1024, el mismo del retrieval).
Se guardan coef_/intercept_ en JSON: la inferencia en produccion es un producto punto, sin
sklearn ni pickle (`src/pipelines/intent_gate.py`).

POR QUE UN CLASIFICADOR Y NO EL COSENO (exp #42): el coseno del embedder esta dominado por el
TOPICO (la intencion gana 1/6 en pares tema-vs-intencion, 1-NN 28.9%). La regresion logistica
aprende QUE dimensiones separan la intencion e ignora las del topico. Medido: F1 0.925 (regex)
-> 0.982 (centroide) -> 0.990 (logreg, 5-fold CV).

TRAIN (composicion elegida midiendo 3 alternativas):
  positivos  16 ejemplos de definicion escritos a mano + 279 del set primario
  negativos  67 ejemplos no-definicion escritos a mano (regulacion/plazo/sancion/calculo/proc.)
⚠️ `queries_fraseos_v1` queda DELIBERADAMENTE FUERA: es el set de test del gate. Meterlo
   contaminaria la medicion e2e — el mismo error que hizo circular al eval original.

  PYTHONPATH=. venv/bin/python -m scripts.train_intent_gate
"""
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from src.pipelines.retrieve import _embed_4b_query

DIM = 1024
OUT = Path("data/intents/gate_definicion_v1.json")
CACHE = Path("data/eval/results/intent_gate/emb_cache.json")


def main():
    L = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]
    ej = L("data/intents/ejemplos_v1.jsonl")
    pos = [e["text"] for e in ej if e["intent"] == "definicion"]
    pos += [q["query"] for q in L("data/eval/queries_balanced_v2_clean.jsonl")
            if q.get("category") == "in_domain"]
    neg = [e["text"] for e in ej if e["intent"] != "definicion"]
    pos, neg = list(dict.fromkeys(pos)), list(dict.fromkeys(neg))
    textos = pos + neg
    y = np.array([1] * len(pos) + [0] * len(neg))
    print(f"train: {len(pos)} positivos / {len(neg)} negativos", flush=True)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    faltan = [t for t in textos if t not in cache]
    if faltan:
        print(f"embebiendo {len(faltan)}", flush=True)
        for i, t in enumerate(faltan):
            v = _embed_4b_query(t)
            if not v:
                raise RuntimeError(f"embedding vacio: {t!r}")
            cache[t] = v[:DIM]
            if (i + 1) % 50 == 0:
                CACHE.write_text(json.dumps(cache)); print(f"  {i+1}/{len(faltan)}", flush=True)
        CACHE.write_text(json.dumps(cache))

    X = np.array([cache[t] for t in textos], dtype=np.float32)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    pred = cross_val_predict(LogisticRegression(max_iter=2000, class_weight="balanced"),
                            X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0))
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    print(f"CV 5-fold: recall {tp/(tp+fn):.3f}  precision {tp/(tp+fp):.3f}", flush=True)

    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(X, y)
    OUT.write_text(json.dumps({
        "modelo": "logreg-binario-definicion",
        "embedder": "qwen3-embedding:4b", "dim": DIM, "normalizado": True,
        "coef": clf.coef_[0].tolist(), "intercept": float(clf.intercept_[0]),
        "train": {"positivos": len(pos), "negativos": len(neg),
                  "excluido": "data/eval/queries_fraseos_v1.jsonl (es el set de test)"},
        "cv5": {"recall": tp / (tp + fn), "precision": tp / (tp + fp)},
    }))
    print(f"escrito {OUT}", flush=True)


if __name__ == "__main__":
    main()
