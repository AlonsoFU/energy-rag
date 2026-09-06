"""Compara el brazo ON de dos corridas de exp_think_paired (misma SET) por query.

Uso: env PYTHONPATH=. venv/bin/python -m scripts.comparar_corridas A_dir B_dir
Ej:  ... data/eval/results/think_real data/eval/results/limpio_dev
Vale porque el pipeline es determinista (ruido_a reprodujo 68/114 exacto): la diferencia
entre corridas es la intervencion, no ruido. Piso de ruido medido igual: cita_ok 6 %,
cita_limpia 30 % (con retrieval identico); mirar p y no solo el delta.
"""
import json, sys
from collections import Counter
from scripts.exp_think_paired import _mcnemar_p

A, B = (json.load(open(f"{d}/result.json"))["detail"] for d in sys.argv[1:3])
b = {r["query"]: r for r in B}
pares = [(a, b[a["query"]]) for a in A if a["query"] in b and a.get("on") and b[a["query"]].get("on")]
print(f"pares: {len(pares)}  (A={len(A)} B={len(B)})")
for m in ("cita_ok", "cita_limpia"):
    xa = sum(bool(a["on"][m]) for a, _ in pares); xb = sum(bool(y["on"][m]) for _, y in pares)
    won = sum(1 for a, y in pares if not a["on"][m] and y["on"][m])
    lost = sum(1 for a, y in pares if a["on"][m] and not y["on"][m])
    print(f"  {m:12} A {xa}/{len(pares)} -> B {xb}/{len(pares)}   [gano {won}, perdio {lost}]  p={_mcnemar_p(won, lost):.4f}")
for lb, k in (("precision", "precision"), ("citas totales", "n_cits"), ("segundos", "secs")):
    va = sum(a["on"].get(k, 0) for a, _ in pares) / len(pares); vb = sum(y["on"].get(k, 0) for _, y in pares) / len(pares)
    print(f"  {lb:14} A {va:6.2f} -> B {vb:6.2f}")
print("  por categoria (cita_ok A->B):")
ca, cb = Counter(), Counter()
for a, y in pares:
    ca[a["category"]] += bool(a["on"]["cita_ok"]); cb[a["category"]] += bool(y["on"]["cita_ok"])
for c in sorted(set(ca) | set(cb)):
    print(f"    {c:16} {ca[c]:3} -> {cb[c]:3}")
