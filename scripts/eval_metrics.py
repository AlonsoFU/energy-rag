"""E1 — métricas de cita más allá de `cita_ok`.

PROBLEMA MEDIDO (GEN8a, 2026-08-08): `cita_ok` = "¿ALGUNA cita pega con el gold?" **premia
ROCIAR**. Con 4.04 citas únicas la precisión media es 0.42 y el sistema acierta; al bajar a 1.80
la precisión sube a 0.64 y el sistema *falla* la métrica. Es decir: toda mejora en la CALIDAD de
la cita se ve como regresión. Mientras esa sea la métrica de adopción, se optimiza el número
equivocado.

Este módulo NO reemplaza `cita_ok` (rompería la comparabilidad con toda la campaña): lo
acompaña con métricas que sí penalizan el ruido.

    cita_ok        ¿alguna cita pega?                         (la histórica; se mantiene)
    cita_first     ¿la PRIMERA cita pega?                     (proxy de compromiso)
    precision      citas únicas correctas / citas únicas
    cita_limpia    pega Y precision >= UMBRAL (default 0.5)   ← candidata a métrica de adopción
    n_uniq         citas únicas por respuesta                 (control de ruido)
    rechazo_ok     en queries `unanswerable`/gold=None: rechazar ES el acierto

Uso:
    PYTHONPATH=. venv/bin/python -m scripts.eval_metrics data/eval/results/gen11_top3/result.json
    PYTHONPATH=. venv/bin/python -m scripts.eval_metrics <path> --arm on
"""
import json, sys
from pathlib import Path
from src.pipelines.grounding import extract_citations, _normalize_art
from src.pipelines.off_topic import REFUSAL_TEXT

UMBRAL_LIMPIA = 0.5


def _golds(row):
    """Acepta filas de eval (expected_norma/also_gold) o ya normalizadas (gold=[...])."""
    if row.get("gold") and isinstance(row["gold"], list):
        out = set()
        for g in row["gold"]:
            if "/" not in str(g):
                continue
            n, a = str(g).split("/", 1)
            if n.lower() == "none":
                continue
            out.add((n, _normalize_art(a)))
        return out
    out = {(str(row["expected_norma"]), _normalize_art(str(row["expected_articulo"])))}
    for g in row.get("also_gold") or []:
        n, a = str(g).split("/", 1); out.add((n, _normalize_art(a)))
    return out


def score_answer(text: str, golds: set, unanswerable: bool = False) -> dict:
    """Métricas de una respuesta. `unanswerable` → rechazar es el acierto."""
    text = text or ""
    refuso = REFUSAL_TEXT.lower() in text.lower()
    cits = [(str(n), _normalize_art(str(a))) for n, a in extract_citations(text)]
    uniq = list(dict.fromkeys(cits))
    good = [c for c in uniq if c in golds]
    prec = (len(good) / len(uniq)) if uniq else 0.0
    if unanswerable:
        return {"unanswerable": True, "rechazo_ok": refuso, "cita_ok": None,
                "cita_first": None, "precision": None, "n_uniq": len(uniq)}
    hit = bool(good) and not refuso
    return {
        "unanswerable": False, "rechazo_ok": None,
        "cita_ok": hit,
        "cita_first": bool(cits) and cits[0] in golds and not refuso,
        "precision": prec,
        "cita_limpia": hit and prec >= UMBRAL_LIMPIA,
        "n_uniq": len(uniq), "n_cits": len(cits), "refuso": refuso,
    }


def report(path: str, arm: str = "off"):
    rows = json.load(open(path))["detail"]
    key = f"{arm}_stats"
    res, rech = [], []
    for r in rows:
        if r.get("err"):
            continue
        txt = (r.get(key) or {}).get("text") if key in r else r.get("text")
        if txt is None:
            continue
        gs = _golds(r)
        una = bool(r.get("unanswerable")) or not gs
        s = score_answer(txt, gs, unanswerable=una)
        (rech if una else res).append((r, s))

    n = len(res)
    if not n:
        print("sin queries contestables en el archivo"); return
    ok = sum(s["cita_ok"] for _, s in res)
    first = sum(s["cita_first"] for _, s in res)
    limpia = sum(s["cita_limpia"] for _, s in res)
    prec = sum(s["precision"] for _, s in res) / n
    uq = sum(s["n_uniq"] for _, s in res) / n

    print(f"=== {Path(path).parent.name} (brazo {arm.upper()}) · {n} contestables ===")
    print(f"  cita_ok      {ok:4}/{n}  = {100*ok/n:5.1f}%   <- metrica historica (premia rociar)")
    print(f"  cita_first   {first:4}/{n}  = {100*first/n:5.1f}%   <- la 1a cita es la correcta")
    print(f"  cita_limpia  {limpia:4}/{n}  = {100*limpia/n:5.1f}%   <- pega Y precision >= {UMBRAL_LIMPIA}")
    print(f"  precision media {prec:.2f}   citas unicas/respuesta {uq:.2f}")
    print(f"  BRECHA cita_ok - cita_limpia: {ok-limpia} respuestas aciertan pero con >50% de citas erradas")
    if rech:
        r_ok = sum(s["rechazo_ok"] for _, s in rech)
        print(f"  rechazo_ok   {r_ok:4}/{len(rech)}  (queries sin respuesta en el corpus)")
    peores = sorted([(s["n_uniq"], s["precision"], r["query"]) for r, s in res if s["cita_ok"] and not s["cita_limpia"]],
                    key=lambda t: (-t[0], t[1]))[:8]
    if peores:
        print("\n  Aciertos MAS RUIDOSOS (cuentan como exito hoy):")
        for u, p, q in peores:
            print(f"    {u:3} citas unicas  precision {p:.2f}  | {q[:52]}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    arm = sys.argv[sys.argv.index("--arm") + 1] if "--arm" in sys.argv else "off"
    report(sys.argv[1], arm)
