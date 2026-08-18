"""B2.2-probe — ¿los embeddings separan por INTENCION o por TEMA?

RIESGO A MEDIR ANTES DE CONSTRUIR: el coseno de un embedder generalista tiende
a agrupar por TOPICO ("peaje" con "peaje") y no por INTENCION ("cómo se calcula"
con "cómo se determina"). Si eso pasa, un clasificador por centroides NO sirve y
hay que cambiar de enfoque (mascara del termino, o modelo liviano supervisado).

Mide 3 cosas, barato (solo embeddings, sin LLM):

  1. LOO-kNN / centroide sobre los 83 ejemplos -> accuracy y matriz de confusion.
  2. TEST TEMA-vs-INTENCION: pares construidos donde el vecino por tema y el
     vecino por intencion son distintos. Cual gana.
  3. Aplicar al set real (queries_fraseos_v1, 64q, todas definicion) -> es la
     metrica que importa: recall de 'definicion' con fraseos naturales.

  PYTHONPATH=. venv/bin/python -m scripts.exp_intent_probe
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

from src.pipelines.retrieve import _embed_4b_query
from src.core import config as cfg

EX = Path("data/intents/ejemplos_v1.jsonl")
FRAS = Path("data/eval/queries_fraseos_v1.jsonl")
DIM = 1024  # MRL, igual que en produccion (embed_4b_dim)
OUT = Path("data/eval/results/intent_probe")

# pares donde tema e intencion apuntan a vecinos DISTINTOS.
# ancla / mismo TEMA-otra intencion / otra tema-MISMA intencion
TEMA_VS_INTENCION = [
    ("cómo se calcula el peaje de transmisión",
     "qué artículo regula el peaje de transmisión",
     "cómo se determina el precio de nudo"),
    ("cuál es el plazo para entregar el balance de transferencias",
     "qué es el balance de transferencias",
     "cuándo debe publicarse el informe de precios de nudo"),
    ("qué multa se aplica por incumplir la norma técnica",
     "qué exige la norma técnica a los coordinados",
     "qué sanción hay por no informar los costos variables"),
    ("qué es el costo marginal",
     "cómo se calcula el costo marginal",
     "qué es la potencia de suficiencia"),
    ("cómo se solicita la conexión de una central",
     "qué norma regula la conexión de una central",
     "cómo se tramita una discrepancia ante el Panel de Expertos"),
    ("cuándo vence el plazo para observar el informe preliminar",
     "cómo se presentan observaciones al informe preliminar",
     "en cuántos días hábiles responde la Comisión"),
]


def cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return num / (na * nb) if na and nb else 0.0


def emb(t, cache):
    if t not in cache:
        v = _embed_4b_query(t)
        if not v:
            raise RuntimeError(f"embedding vacio: {t!r}")
        cache[t] = v[:DIM]
    return cache[t]


def centroide(vs):
    n = len(vs)
    return [sum(v[i] for v in vs) / n for i in range(len(vs[0]))]


def main():
    cfg.settings.embed_4b_dim = DIM
    OUT.mkdir(parents=True, exist_ok=True)
    cache = {}
    ex = [json.loads(l) for l in EX.read_text().splitlines() if l.strip()]
    print(f"=== embebiendo {len(ex)} ejemplos (dim {DIM}) ===", flush=True)
    for e in ex:
        emb(e["text"], cache)

    por_intent = defaultdict(list)
    for e in ex:
        por_intent[e["intent"]].append(e["text"])
    intents = sorted(por_intent)

    # ---- 1. LOO: centroide y 1-NN ----
    conf_c, conf_k = Counter(), Counter()
    for e in ex:
        # centroide dejando fuera el propio ejemplo
        cents = {}
        for it in intents:
            vs = [emb(t, cache) for t in por_intent[it] if t != e["text"]]
            cents[it] = centroide(vs)
        v = emb(e["text"], cache)
        pred_c = max(cents, key=lambda it: cos(v, cents[it]))
        pred_k = max(((cos(v, emb(o["text"], cache)), o["intent"])
                      for o in ex if o["text"] != e["text"]))[1]
        conf_c[(e["intent"], pred_c)] += 1
        conf_k[(e["intent"], pred_k)] += 1

    n = len(ex)
    for lbl, conf in (("CENTROIDE", conf_c), ("1-NN", conf_k)):
        acc = sum(v for (g, p), v in conf.items() if g == p)
        print(f"\n=== 1. LOO {lbl}: {acc}/{n} = {100*acc/n:.1f}% ===", flush=True)
        print("      " + "".join(f"{i[:6]:>8}" for i in intents) + "   <- predicho", flush=True)
        for g in intents:
            fila = "".join(f"{conf.get((g, p), 0):>8}" for p in intents)
            print(f"{g[:6]:>6}" + fila, flush=True)

    # ---- 2. tema vs intencion ----
    print("\n=== 2. TEMA vs INTENCION (gana el mas cercano al ancla) ===", flush=True)
    gana_intencion = 0
    for ancla, mismo_tema, misma_int in TEMA_VS_INTENCION:
        a = emb(ancla, cache)
        st, si = cos(a, emb(mismo_tema, cache)), cos(a, emb(misma_int, cache))
        ok = si > st
        gana_intencion += ok
        print(f"  {'INTENCION' if ok else 'TEMA     '}  tema={st:.4f} int={si:.4f}  "
              f"| {ancla[:44]}", flush=True)
    print(f"  -> la INTENCION gana {gana_intencion}/{len(TEMA_VS_INTENCION)}", flush=True)

    # ---- 3. set real: 64 queries, todas 'definicion' ----
    fr = [json.loads(l) for l in FRAS.read_text().splitlines() if l.strip()]
    cents = {it: centroide([emb(t, cache) for t in por_intent[it]]) for it in intents}
    print(f"\n=== 3. queries_fraseos_v1 ({len(fr)}q, todas definicion) ===", flush=True)
    pred = Counter()
    margenes, fallas = [], []
    for q in fr:
        v = emb(q["query"], cache)
        sims = sorted(((cos(v, cents[it]), it) for it in intents), reverse=True)
        pred[sims[0][1]] += 1
        margenes.append(sims[0][0] - sims[1][0])
        if sims[0][1] != "definicion":
            fallas.append((q["_grupo"], q["query"], sims[0][1], sims[0][0], sims[1][1]))
    ok = pred["definicion"]
    print(f"  recall definicion: {ok}/{len(fr)} = {100*ok/len(fr):.1f}%", flush=True)
    print(f"  predicciones: {dict(pred)}", flush=True)
    print(f"  margen 1o-2o medio: {sum(margenes)/len(margenes):.4f}", flush=True)
    for g, q, p, s, seg in fallas:
        print(f"    [{g}] -> {p} ({s:.4f}, 2o {seg})  {q[:52]}", flush=True)

    (OUT / "probe.json").write_text(json.dumps({
        "loo_centroide": {f"{g}->{p}": v for (g, p), v in conf_c.items()},
        "loo_1nn": {f"{g}->{p}": v for (g, p), v in conf_k.items()},
        "tema_vs_intencion": f"{gana_intencion}/{len(TEMA_VS_INTENCION)}",
        "fraseos_recall_definicion": f"{ok}/{len(fr)}",
        "fraseos_pred": dict(pred),
    }, ensure_ascii=False, indent=2))
    print(f"\nescrito {OUT}/probe.json", flush=True)


if __name__ == "__main__":
    main()
