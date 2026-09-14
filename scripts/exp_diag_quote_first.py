"""Diagnostico del 17 %: por que quote-only cae a prosa en el held-out.

Hallazgo previo (2026-09-14): 10 de las 11 respuestas en prosa de `qonly2_holdout` citan el
glosario Art. 13 de 250604. La hipotesis de las notas BCN quedo DESCARTADA: solo 1 de 9
definiciones que fallan tiene una nota adentro, y hay definiciones del MISMO glosario que si
verifican. El presupuesto de caracteres tampoco (45000 contra 9889).

Corre la ruta real (retrieval + generate_answer) sobre las preguntas que cayeron a prosa y
registra, por pregunta: claves de los docs (y si una clave llega con textos distintos), el
texto crudo de la extraccion y lo que verifico. No escribe en la DB. El nombre empieza con
`exp_` para que `gpu_vigia.sh` lo reconozca como trabajo y lo vigile.

  env PYTHONPATH=. SET=<jsonl> NAME=<dir> SOLO_ON=1 OUT=<jsonl> venv/bin/python -m scripts.exp_diag_quote_first
"""
import json, os
import src.pipelines.generate as G
from src.pipelines.grounding import _normalize_art

OUT = os.environ["OUT"]
_orig = G._quote_first


def _espia(query, docs, llm, model, max_q):
    qs, resp = _orig(query, docs, llm, model, max_q)
    claves = {}
    for d in docs:
        k = f"{d['id_norma']}|{_normalize_art(str(d['articulo_numero']))}"
        claves.setdefault(k, set()).add(len(d.get("articulo_text") or ""))
    with open(OUT, "a") as f:
        f.write(json.dumps({
            "query": query,
            "docs": [{"k": f"{d['id_norma']}|{d['articulo_numero']}",
                      "len": len(d.get("articulo_text") or ""), "id": d.get("id")} for d in docs],
            "claves_con_textos_distintos": {k: sorted(v) for k, v in claves.items() if len(v) > 1},
            "crudo": G._strip_think_block(resp.text),
            "verificadas": [list(x) for x in qs],
            "textos": {f"{d['id_norma']}|{d['articulo_numero']}|{len(d.get('articulo_text') or '')}":
                       d.get("articulo_text") for d in docs},
        }, ensure_ascii=False) + "\n")
    return qs, resp


G._quote_first = _espia  # generate_answer lo busca como global del modulo en cada llamada

import scripts.exp_think_paired as E  # noqa: E402  (lee SET/NAME/SOLO_ON al importar)
E.main()
