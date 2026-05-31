"""Diagnóstico (solo-lectura): ¿find_subject_concept detecta el concepto en
queries PARAFRASEADAS? Corre sobre queries_independent.jsonl filtrando por
categoría (default indep_complex). No genera, no inyecta, no toca la DB salvo
lectura. Imprime: detección sí/no, (norma,art) detectado vs gold, y si coincide.
"""
import json
import sys
from pathlib import Path

from src.pipelines.concept_injection import find_subject_concept

EVAL = Path("data/eval/queries_independent.jsonl")


def main():
    cats = set(sys.argv[1:]) or {"indep_complex"}
    rows = [json.loads(l) for l in EVAL.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r["category"] in cats]

    detected = matched = 0
    print(f"== {len(rows)} queries en {sorted(cats)} ==\n")
    for r in rows:
        q = r["query"]
        gold_n, gold_a = str(r["expected_norma"]), str(r["expected_articulo"])
        res = find_subject_concept(q)
        if res is None:
            print(f"[NO DETECTA] gold={gold_n}/{gold_a}")
            print(f"             {q}\n")
            continue
        detected += 1
        norma, art, _def, canon, alias = res
        ok = (str(norma) == gold_n and str(art) == gold_a)
        matched += ok
        tag = "OK   " if ok else "MISS "
        print(f"[DETECTA {tag}] det={norma}/{art}  gold={gold_n}/{gold_a}  concepto='{canon}'")
        print(f"             {q}\n")

    n = len(rows)
    print(f"== RESUMEN ==")
    print(f"detecta concepto : {detected}/{n}")
    print(f"detecta Y acierta: {matched}/{n}")
    print(f"NO detecta       : {n - detected}/{n}")


if __name__ == "__main__":
    main()
