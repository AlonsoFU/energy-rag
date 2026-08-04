"""E0b: audita y LIMPIA los golds de balanced_v2 (in_domain). Instantaneo (sin gen).
Fuente autoritativa de 'donde se define X' = fragmentos_definicion (termino -> id_norma/numero)
+ verificacion de que el articulo-gold mencione el concepto. Produce balanced_v2_clean.jsonl
con also_gold (todas las normas que definen el concepto) y flags de golds rotos.

Uso: PYTHONPATH=. venv/bin/python -m scripts.audit_golds
"""
import re, json
from pathlib import Path
from src.storage.connection import with_connection

SRC = Path("data/eval/queries_balanced_v2.jsonl")
OUT = Path("data/eval/queries_balanced_v2_clean.jsonl")


def concept(q):
    return re.sub(r'^(qu[eé] es|qu[eé] son|qu[eé] significa|definici[oó]n de|qu[eé] se entiende por|concepto de|significado de)\s+',
                  '', q.strip(), flags=re.I).strip()


def _norm_num(s):
    return re.sub(r'[°º\s]', '', str(s)).lower()


def main():
    rows = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    with with_connection() as conn, conn.cursor() as cur:
        # mapa termino(lower) -> set de (id_norma, numero) donde se define (glosario)
        cur.execute("SELECT lower(termino), id_norma, numero FROM fragmentos_definicion")
        defmap = {}
        for t, n, num in cur.fetchall():
            defmap.setdefault(t, set()).add((str(n), str(num)))
        # todos los articulos (para verificar mencion + resolver formato de numero)
        cur.execute("SELECT id_norma, numero, texto FROM articulos WHERE texto IS NOT NULL")
        arts = cur.fetchall()
    art_by_norma = {}
    for n, num, txt in arts:
        art_by_norma.setdefault(str(n), []).append((str(num), txt or ""))

    stats = {"valid": 0, "fixed_format": 0, "also_gold_added": 0, "broken": 0, "notindomain": 0}
    out_rows = []
    for q in rows:
        if q.get("category") != "in_domain":
            out_rows.append(q); stats["notindomain"] += 1; continue
        c = concept(q["query"]); cl = c.lower()
        gN, gA = str(q["expected_norma"]), str(q["expected_articulo"])
        # 1) also_gold desde el glosario: todas las normas/arts que definen c (exacto o substring)
        deflocs = set(defmap.get(cl, set()))
        for t, locs in defmap.items():
            if t == cl or (len(cl) > 4 and (cl in t or t in cl)):
                deflocs |= locs
        also = sorted({f"{n}/{a}" for n, a in deflocs if not (n == gN and _norm_num(a) == _norm_num(gA))})
        # 2) verifica gold: articulo existe + menciona el concepto
        gold_txt = ""
        for num, txt in art_by_norma.get(gN, []):
            if _norm_num(num) == _norm_num(gA):
                gold_txt = txt; break
        w = cl.split()[0]
        gold_mentions = w in gold_txt.lower() if gold_txt else False
        gold_in_def = any(n == gN and _norm_num(a) == _norm_num(gA) for n, a in deflocs)

        nq = dict(q)
        if also:
            nq["also_gold"] = also; stats["also_gold_added"] += 1
        if gold_mentions or gold_in_def:
            stats["valid"] += 1
        elif also:
            # gold-art no menciona el concepto PERO el glosario si lo define -> gold roto,
            # promueve el 1er also_gold a gold principal
            fixN, fixA = also[0].split("/", 1)
            nq["expected_norma"], nq["expected_articulo"] = fixN, fixA
            nq["also_gold"] = [f"{gN}/{gA}"] + [g for g in also[1:]]
            nq["_gold_fixed_from"] = f"{gN}/{gA}"; stats["fixed_format"] += 1
        else:
            nq["_gold_suspect"] = True; stats["broken"] += 1
        out_rows.append(nq)

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n")
    print("=== E0b audit golds (in_domain) ===")
    for k, v in stats.items():
        print(f"  {k:18s} {v}")
    print(f"\nescrito {OUT} ({len(out_rows)} filas)")
    print("\n=== golds SOSPECHOSOS (ni el art menciona el concepto ni hay glosario) ===")
    for r in out_rows:
        if r.get("_gold_suspect"):
            print(f"  {concept(r['query'])[:32]:32s} gold={r['expected_norma']}/{r['expected_articulo']}")
    print("\n=== golds CORREGIDOS (promovidos desde glosario) ===")
    for r in out_rows:
        if r.get("_gold_fixed_from"):
            print(f"  {concept(r['query'])[:28]:28s} {r['_gold_fixed_from']} -> {r['expected_norma']}/{r['expected_articulo']}")


if __name__ == "__main__":
    main()
