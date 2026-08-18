#!/usr/bin/env python3
"""B1.1 - Set de fraseos variados (queries_fraseos_v1.jsonl).

Motivo: las 279 queries in_domain del set primario usan SOLO 3 plantillas
("qué es X" / "definición de X" / "qué significa X"), que son las MISMAS que
cubre el regex `_DEF_INTENT`. El eval se mide contra sí mismo.

Este script genera fraseos NATURALES sobre los MISMOS terminos (mismo gold,
sin re-auditar) en dos grupos, que corresponden a dos fallas distintas:

  grupo A  el gate `_is_definition_query` NO dispara
           -> glossary_inject nunca corre. 10 plantillas.
  grupo B  el gate SI dispara pero `_definition_concept` devuelve la query
           ENTERA en vez del termino -> def_exact no encuentra nada y
           glossary_inject tampoco corre. 8 plantillas.

Solo se usan terminos con ok_off=True en la ultima corrida pareada
(gen13_roles), para que una falla sea atribuible al FRASEO y no al termino.
=> el drop medido es una COTA INFERIOR del efecto del fraseo.

Control pareado: cada fila trae `control_query` = "qué es <termino>", cuyo
resultado ya esta medido.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.pipelines.retrieve import _is_definition_query, _definition_concept  # noqa: E402

SRC = ROOT / "data/eval/queries_balanced_v2_clean.jsonl"
RES = ROOT / "data/eval/results/gen13_roles/result.json"
OUT = ROOT / "data/eval/queries_fraseos_v1.jsonl"

# grupo A: el gate NO dispara
TPL_A = [
    "cómo se define {T}",
    "defíneme {T}",
    "{T} definición",
    "qué entiende la ley por {T}",
    "en qué consiste {T}",
    "qué quiere decir {T}",
    "a qué se le llama {T}",
    "cómo define la ley {T}",
    "explícame el término {T}",
    "qué se debe entender por {T}",
]
# grupo B: el gate dispara pero la extraccion del concepto falla
TPL_B = [
    "dame la definición de {T}",
    "cuál es la definición de {T}",
    "necesito saber qué es {T}",
    "explícame qué significa {T}",
    "me puedes decir qué es {T}",
    "según la ley, qué es {T}",
    "en la normativa, qué se entiende por {T}",
    "quisiera el concepto de {T}",
]
N_A, N_B = 4, 3  # terminos por plantilla


def main() -> int:
    rows = [json.loads(l) for l in SRC.open()]
    ok_off = {d["query"]: d["ok_off"] for d in json.load(RES.open())["detail"]}

    # terminos en orden estable, solo los que hoy aciertan
    terms = []
    for r in rows:
        if r["category"] != "in_domain" or not r["query"].startswith("qué es "):
            continue
        if ok_off.get(r["query"]) is not True:
            continue
        terms.append((r["query"][len("qué es "):], r))

    need = len(TPL_A) * N_A + len(TPL_B) * N_B
    if len(terms) < need:
        print(f"ERROR: {len(terms)} terminos disponibles, se necesitan {need}")
        return 1

    plan = [("A", t) for t in TPL_A for _ in range(N_A)]
    plan += [("B", t) for t in TPL_B for _ in range(N_B)]

    out, bad = [], []
    for (grp, tpl), (term, src) in zip(plan, terms):
        q = tpl.format(T=term)
        gate = _is_definition_query(q)
        concept = _definition_concept(q)
        # invariante del grupo: A no pasa el gate; B pasa pero extrae mal
        if grp == "A" and gate:
            bad.append(("A-cubierta-por-el-gate", q))
        if grp == "B" and (not gate or concept == term):
            bad.append(("B-extraccion-correcta", q))
        out.append({
            "query": q,
            "expected_norma": src["expected_norma"],
            "expected_articulo": src["expected_articulo"],
            "category": "in_domain",
            "also_gold": src.get("also_gold", []),
            "_grupo": grp,
            "_plantilla": tpl,
            "_termino": term,
            "_control_query": src["query"],
            "_gate_actual": gate,
            "_concepto_extraido": concept,
        })

    if bad:
        print(f"AVISO: {len(bad)} filas violan la invariante de su grupo:")
        for why, q in bad[:10]:
            print(f"  {why}: {q}")

    with OUT.open("w") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    na = sum(1 for r in out if r["_grupo"] == "A")
    print(f"escrito {OUT.relative_to(ROOT)}: {len(out)} queries "
          f"(A={na} gate-no-dispara, B={len(out) - na} extraccion-rota), "
          f"{len({r['_termino'] for r in out})} terminos distintos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
