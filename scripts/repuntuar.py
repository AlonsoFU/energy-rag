"""Re-puntuar corridas ya hechas con el scorer CORRECTO — sin volver a usar la GPU.

Motivo: `exp_lookup_paired` / `exp_veto_offtopic` puntuaban toda query con `cita_ok`, incluidas
las **off-corpus** (`gold=None`), donde RECHAZAR ES EL ACIERTO. `queries_operativas_v1` tiene 4
(`hold_offcorpus`: "cómo hacer un queque de zanahoria", "capital de Australia", "quién pintó la
Mona Lisa", "dosis de paracetamol"), y las tres corridas sobre ese set las contaron como fallo.

Es la regla #2 del proyecto ("todo scorer nuevo declara cómo puntúa el RECHAZO antes de
correrse"), fallada por tercera vez. Se puede arreglar sin re-correr porque el TEXTO de cada
respuesta está persistido (regla #5) — exactamente para esto.

  PYTHONPATH=. venv/bin/python -m scripts.repuntuar <NAME> [<NAME> ...]
"""
import json
import math
import sys
from pathlib import Path

from src.pipelines.off_topic import REFUSAL_TEXT


def _mcnemar_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def _es_offcorpus(q):
    """Fuera del corpus => RECHAZAR es el acierto.

    Se decide por CATEGORIA, no por `gold=None`. Sin gold hay dos casos distintos y
    mezclarlos vuelve a falsear la medicion:
      hold_offcorpus  "capital de Australia"  -> rechazar ES el acierto
      hold_ambiguo    "que es la comision"    -> el termino SI esta en el corpus; el gold esta
                                                 vacio porque se espera que el sistema PREGUNTE,
                                                 no que rechace ni que afirme. Es el frente D4.
    """
    return str(q.get("category", "")).lower() == "hold_offcorpus"


def _es_ambigua(q):
    return str(q.get("category", "")).lower() == "hold_ambiguo"


def acierto(q, brazo):
    st = q[brazo]
    refuso = bool(st.get("refuso")) or REFUSAL_TEXT.lower() in (st.get("text") or "").lower()
    if _es_offcorpus(q):
        return refuso          # rechazar ES el acierto
    return bool(st.get("cita_ok"))


def main(nombres):
    for name in nombres:
        p = Path(f"data/eval/results/{name}/result.json")
        if not p.exists():
            print(f"{name}: no existe"); continue
        d = [q for q in json.load(p.open())["detail"] if q.get("on") and q.get("off")]
        offc = [q for q in d if _es_offcorpus(q)]
        amb = [q for q in d if _es_ambigua(q)]
        a = sum(acierto(q, "off") for q in d)
        b = sum(acierto(q, "on") for q in d)
        won = sum(1 for q in d if not acierto(q, "off") and acierto(q, "on"))
        lost = sum(1 for q in d if acierto(q, "off") and not acierto(q, "on"))
        # como se veia con el scorer viejo
        va = sum(q["off"]["cita_ok"] for q in d)
        vb = sum(q["on"]["cita_ok"] for q in d)
        print(f"\n=== {name} ({len(d)} pares, {len(offc)} off-corpus) ===")
        print(f"  scorer VIEJO (rechazo = fallo)     OFF {va}/{len(d)}  ->  ON {vb}/{len(d)}")
        print(f"  scorer CORRECTO (rechazo = acierto) OFF {a}/{len(d)}  ->  ON {b}/{len(d)}"
              f"   [gano {won}, perdio {lost}]  p={_mcnemar_p(lost, won):.4f}")
        if offc:
            ok_off = sum(acierto(q, "off") for q in offc)
            ok_on = sum(acierto(q, "on") for q in offc)
            print(f"  off-corpus rechazadas correctamente: OFF {ok_off}/{len(offc)} · ON {ok_on}/{len(offc)}")
        if amb:
            print(f"  ⚠️ {len(amb)} queries AMBIGUAS ({', '.join(q['query'][:26] for q in amb)}): el sistema")
            print(f"     AFIRMA una de las acepciones en vez de preguntar. Ningun scorer actual lo mide (frente D4).")


if __name__ == "__main__":
    main(sys.argv[1:] or ["gate_noregresion", "post_reingesta_op", "veto_operativas"])
