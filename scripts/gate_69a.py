"""Gate de #69a-bis: aplica el criterio fijado en plan v37 y REVIERTE solo si falla. Corre en la cola.

Criterio (el ORIGINAL de #69a, contra la base de la config adoptada sobre el mismo corpus previo):
  cita_ok NO cae > 3  Y  cita_limpia NO cae, en dev (combo0_dev -> l69_dev) Y held-out
  (combo0_holdout -> l69_holdout). Falla -> reembeber --revertir + limpiar --revertir.
"""
import json, subprocess, sys
R = "data/eval/results/"


def tot(n, k):
    return sum(bool(d["on"][k]) for d in json.load(open(f"{R}{n}/result.json"))["detail"] if d.get("on"))


ok = True
for base, nuevo in (("combo0_dev", "l69_dev"), ("combo0_holdout", "l69_holdout")):
    d_ok, d_li = tot(nuevo, "cita_ok") - tot(base, "cita_ok"), tot(nuevo, "cita_limpia") - tot(base, "cita_limpia")
    pasa = d_ok >= -3 and d_li >= 0
    ok &= pasa
    print(f"{base} -> {nuevo}: cita_ok {d_ok:+d}  cita_limpia {d_li:+d}  {'PASA' if pasa else 'FALLA'}")
if ok:
    print("VEREDICTO: #69a SE QUEDA"); sys.exit(0)
print("VEREDICTO: #69a FALLA -> revirtiendo vectores y texto")
for m in ("scripts.reembeber_limpiados", "scripts.limpiar_notas_bcn"):
    print(subprocess.run(["venv/bin/python", "-m", m, "--revertir"], capture_output=True, text=True).stdout[-400:])
