"""B2 (pendiente) — clasificador MULTI-CLASE de intención: las 5 que quedaron sin usar.

El gate adoptado (`intent_gate`) es BINARIO: definición / no-definición. Los 67 ejemplos de
regulación · plazo · sanción · cálculo · procedimiento están escritos en
`data/intents/ejemplos_v1.jsonl` desde B2.1 y no alimentan nada.

Esto entrena el multi-clase y —lo importante— MIDE si es usable, porque el probe #42 mostró que
el coseno agrupa por TÓPICO y no por intención (1-NN 28.9%, la intención gana 1/6 en pares
tema-vs-intención). La pregunta es si la logreg lo salva también en 6 clases, no solo en 2.

Guarda coeficientes en `data/intents/intent_multi_v1.json` (producto punto en runtime, sin
sklearn ni pickle), igual que el gate binario.

  PYTHONPATH=. venv/bin/python -m scripts.train_intent_multi
"""
import json
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from src.pipelines.retrieve import _embed_4b_query

DIM = 1024
EJ = Path("data/intents/ejemplos_v1.jsonl")
OUT = Path("data/intents/intent_multi_v1.json")
CACHE = Path("data/eval/results/intent_gate/emb_cache.json")


def main():
    ej = [json.loads(l) for l in EJ.read_text().splitlines() if l.strip()]
    textos = [e["text"] for e in ej]
    y = np.array([e["intent"] for e in ej])
    print(f"ejemplos: {len(ej)}  {dict(Counter(y))}", flush=True)

    CACHE.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    faltan = [t for t in textos if t not in cache]
    for i, t in enumerate(faltan):
        v = _embed_4b_query(t)
        if not v:
            raise RuntimeError(f"embedding vacio: {t!r}")
        cache[t] = v[:DIM]
    if faltan:
        CACHE.write_text(json.dumps(cache))
        print(f"embebidos {len(faltan)} nuevos", flush=True)

    X = np.array([cache[t] for t in textos], dtype=np.float32)
    X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)

    clases = sorted(set(y))
    # con ~14 ejemplos por clase, 5-fold deja ~11 para entrenar: es poco y hay que decirlo.
    pred = cross_val_predict(LogisticRegression(max_iter=3000, class_weight="balanced"),
                             X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0))
    acc = float((pred == y).mean())
    print(f"\n=== LOO/CV5 multi-clase: {int((pred==y).sum())}/{len(y)} = {100*acc:.1f}% "
          f"(azar = {100/len(clases):.1f}%) ===", flush=True)
    print("      " + "".join(f"{c[:6]:>9}" for c in clases) + "   <- predicho", flush=True)
    for g in clases:
        fila = "".join(f"{int(((y == g) & (pred == p)).sum()):>9}" for p in clases)
        print(f"{g[:6]:>6}" + fila, flush=True)
    print("\npor clase:", flush=True)
    for c in clases:
        m = y == c
        r = float((pred[m] == c).mean())
        p = float((y[pred == c] == c).mean()) if (pred == c).any() else 0.0
        print(f"   {c:14} recall {r:.2f}  precision {p:.2f}  (n={int(m.sum())})", flush=True)

    clf = LogisticRegression(max_iter=3000, class_weight="balanced").fit(X, y)
    OUT.write_text(json.dumps({
        "modelo": "logreg-multiclase-intencion",
        "embedder": "qwen3-embedding:4b", "dim": DIM, "normalizado": True,
        "clases": list(clf.classes_),
        "coef": clf.coef_.tolist(), "intercept": clf.intercept_.tolist(),
        "cv5_accuracy": acc,
        "n_entrenamiento": {c: int((y == c).sum()) for c in clases},
        "caveat": ("~14 ejemplos por clase, TODOS escritos por el asistente. El sesgo del autor "
                   "queda en los coeficientes; hacen falta queries reales del usuario."),
    }))
    print(f"\nescrito {OUT}", flush=True)


if __name__ == "__main__":
    main()
