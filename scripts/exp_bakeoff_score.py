"""Scoring regresión-aware del bake-off de generación. Lee gen_bakeoff/result.json (detalle por
query) y muestra, por modelo: cita_ok por set, TOTAL, y vs baseline 9b: GANA-N (el modelo acierta
y 9b no) / ROMPE-N (9b acierta y el modelo no). Ganador = mejor NETO sin romper, no solo coloquial.

Uso: PYTHONPATH=. venv/bin/python -m scripts.exp_bakeoff_score [baseline_model]
"""
import json, sys
from pathlib import Path

RJ = Path("data/eval/results/gen_bakeoff/result.json")


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "ollama/qwen3.5:9b"
    d = json.loads(RJ.read_text())
    detail = d["detail"]
    models = [m for m in d["agg"].keys()]
    ns = {}
    for c in detail:
        ns[c["set"]] = ns.get(c["set"], 0) + 1
    print(f"baseline = {base}   (sets: {ns})\n", flush=True)
    print(f"{'modelo':26s} {'coloq':>5s} {'dev':>4s} {'hold':>4s} {'TOT':>4s} {'GANA':>5s} {'ROMPE':>6s} {'NETO':>5s}", flush=True)
    rows = []
    for m in models:
        per = {s: 0 for s in ns}
        gana = rompe = 0
        for c in detail:
            ok = c.get(f"ok::{m}")
            okb = c.get(f"ok::{base}")
            if ok:
                per[c["set"]] += 1
            if ok and not okb:
                gana += 1
            if okb and not ok:
                rompe += 1
        tot = sum(per.values())
        rows.append((tot, m, per, gana, rompe))
    for tot, m, per, gana, rompe in sorted(rows, reverse=True):
        neto = gana - rompe
        print(f"{m.replace('ollama/',''):26s} {per.get('coloquial',0):>5d} {per.get('dev',0):>4d} "
              f"{per.get('holdout',0):>4d} {tot:>4d} {gana:>5d} {rompe:>6d} {neto:>+5d}", flush=True)
    print("\nGANA/ROMPE/NETO = vs baseline. Ganador = mayor TOT con ROMPE bajo (no rompe dev/holdout).", flush=True)


if __name__ == "__main__":
    main()
