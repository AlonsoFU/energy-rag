"""Reporte automático de un experimento pareado, SIN intervención.

Pensado para correr desde la cola al terminar cada experimento: lee el result.json,
calcula cita_ok + McNemar + las métricas de precisión (E1) y APENDA el resultado a
`docs/resultados-auto.md`. Así, si la sesión se corta, los números quedan escritos.

Uso:  PYTHONPATH=. venv/bin/python -m scripts.auto_report <nombre_experimento> "<descripcion>"
      (busca data/eval/results/<nombre>/result.json)
"""
import json, math, sys
from pathlib import Path
from datetime import datetime
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT

OUT = Path("docs/resultados-auto.md")
UMBRALES = (0.5, 1.0)


def _golds(r):
    out = {(str(r["expected_norma"]), _normalize_art(str(r["expected_articulo"])))}
    for g in r.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def _mcnemar_p(b, c):
    n = b + c
    if n == 0: return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def _stats(text, gs):
    text = text or ""
    refuso = REFUSAL_TEXT.lower() in text.lower()
    cits = [(str(n), _normalize_art(str(a))) for n, a in extract_citations(text)]
    uniq = list(dict.fromkeys(cits))
    good = [c for c in uniq if c in gs]
    prec = (len(good) / len(uniq)) if uniq else 0.0
    hit = bool(good) and not refuso
    return {"ok": hit, "prec": prec, "n_uniq": len(uniq),
            "limpia": {u: (hit and prec >= u) for u in UMBRALES}}


def main(name: str, desc: str = ""):
    path = Path(f"data/eval/results/{name}/result.json")
    if not path.exists():
        print(f"[auto_report] falta {path}"); return
    rows = [r for r in json.load(open(path))["detail"] if not r.get("err") and r.get("off_stats")]
    if not rows:
        print("[auto_report] sin filas validas"); return

    agg = {"off": [], "on": []}
    for r in rows:
        gs = _golds(r)
        for arm in ("off", "on"):
            agg[arm].append(_stats(r[f"{arm}_stats"]["text"], gs))

    n = len(rows)
    ok = {a: sum(s["ok"] for s in agg[a]) for a in agg}
    won = sum(1 for i in range(n) if agg["on"][i]["ok"] and not agg["off"][i]["ok"])
    lost = sum(1 for i in range(n) if agg["off"][i]["ok"] and not agg["on"][i]["ok"])
    p = _mcnemar_p(lost, won)
    veredicto = "SIGNIFICATIVO" if p < 0.05 else "ruido/flat"
    if p < 0.05:
        veredicto += " POSITIVO" if won > lost else " NEGATIVO"

    lines = [
        f"\n## {name} — {datetime.now():%Y-%m-%d %H:%M}",
        f"{desc}\n" if desc else "",
        "```",
        f"cita_ok      OFF {ok['off']:3}/{n}  ->  ON {ok['on']:3}/{n}   (gano {won}, perdio {lost})",
        f"McNemar p={p:.4f}  ({veredicto})",
    ]
    for u in UMBRALES:
        a = sum(s["limpia"][u] for s in agg["off"]); b = sum(s["limpia"][u] for s in agg["on"])
        etq = "cita_limpia(>=0.5)" if u == 0.5 else "cita_perfecta(1.0) "
        lines.append(f"{etq}  OFF {a:3}/{n}  ->  ON {b:3}/{n}   ({b-a:+d})")
    for lbl, k in (("precision   ", "prec"), ("citas unicas", "n_uniq")):
        a = sum(s[k] for s in agg["off"]) / n; b = sum(s[k] for s in agg["on"]) / n
        lines.append(f"{lbl}        OFF {a:6.2f}      ->  ON {b:6.2f}")
    lines.append("```")

    flips = [(rows[i]["query"], agg["on"][i]["ok"]) for i in range(n)
             if agg["on"][i]["ok"] != agg["off"][i]["ok"]]
    if flips:
        lines.append("\nFlips:")
        for q, gano in flips[:20]:
            lines.append(f"- {'GANA ' if gano else 'PIERDE'} `{q[:60]}`")

    # lectura automatica: adoptar solo si no regresiona cita_ok y mejora precision
    d_ok = ok["on"] - ok["off"]
    d_lim = sum(s["limpia"][0.5] for s in agg["on"]) - sum(s["limpia"][0.5] for s in agg["off"])
    if d_ok >= 0 and d_lim > 0:
        lines.append(f"\n**LECTURA AUTOMATICA: candidato a ADOPTAR** (cita_ok {d_ok:+d}, cita_limpia {d_lim:+d}).")
    elif d_ok < 0 and d_lim > 0:
        lines.append(f"\n**LECTURA AUTOMATICA: TRADE-OFF** (cita_ok {d_ok:+d} pero cita_limpia {d_lim:+d}) — decision de producto, NO adoptar solo.")
    else:
        lines.append(f"\n**LECTURA AUTOMATICA: no adoptar** (cita_ok {d_ok:+d}, cita_limpia {d_lim:+d}).")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write("\n".join(x for x in lines if x is not None) + "\n")
    print("\n".join(x for x in lines if x is not None), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "")
