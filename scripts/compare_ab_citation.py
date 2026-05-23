"""Compare cited_expected between a baseline run (full-article inject) and a
treatment run (focused-definition inject) over the SAME queries.

Reports, per category bucket:
  - recovered: was a citation MISS in baseline, now a HIT
  - regressed: was a HIT in baseline, now a MISS
  - net change in cited_expected and definition_recall

Usage:
    PYTHONPATH=. ./venv/bin/python scripts/compare_ab_citation.py \
        --baseline data/eval/results/<baseline>.json \
        --treatment data/eval/results/<treatment>.json
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path

from src.eval.correctness import cited_expected, definition_recall
from src.pipelines.concept_injection import extract_definitional_term
from src.pipelines.normalize import normalize_for_match
from src.storage.connection import with_connection


@lru_cache(maxsize=1)
def _def_index() -> dict[str, str]:
    out: dict[str, str] = {}
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre, aliases, definicion FROM conceptos")
        for nombre, aliases, definicion in cur.fetchall():
            if not definicion:
                continue
            for name in [nombre, *(aliases or [])]:
                k = normalize_for_match(str(name))
                if k:
                    out.setdefault(k, definicion)
    return out


def _definition_for(query: str) -> str | None:
    term = extract_definitional_term(query)
    if term is None:
        return None
    return _def_index().get(normalize_for_match(term))


def _score(row: dict) -> tuple[bool, float]:
    definition = _definition_for(row["query"])
    cited = cited_expected(row.get("citations"), row.get("expected_norma"),
                           row.get("expected_articulo"))
    drec = definition_recall(row.get("answer", ""), definition or "")
    return cited, drec


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", type=Path, required=True)
    p.add_argument("--treatment", type=Path, required=True)
    a = p.parse_args()

    base = {r["query"]: r for r in json.loads(a.baseline.read_text())["per_query"]}
    treat = {r["query"]: r for r in json.loads(a.treatment.read_text())["per_query"]}
    common = [q for q in treat if q in base]

    in_dom = [q for q in common if treat[q].get("category") == "in_domain"]
    off_c = [q for q in common if treat[q].get("category") == "off_corpus"]

    recovered, regressed = [], []
    bc = tc = 0
    bd = td = 0.0
    for q in in_dom:
        b_cited, b_drec = _score(base[q])
        t_cited, t_drec = _score(treat[q])
        bc += b_cited
        tc += t_cited
        bd += b_drec
        td += t_drec
        if t_cited and not b_cited:
            recovered.append(q)
        if b_cited and not t_cited:
            regressed.append(q)

    n = len(in_dom)
    print(f"in_domain comparadas: {n}")
    print(f"  cited_expected  baseline {bc}/{n} ({100*bc/n:.1f}%) "
          f"→ treatment {tc}/{n} ({100*tc/n:.1f}%)  Δ {tc-bc:+d}")
    print(f"  def_recall mean baseline {bd/n:.3f} → treatment {td/n:.3f}")
    print(f"  RECOVERED (miss→hit): {len(recovered)}")
    print(f"  REGRESSED (hit→miss): {len(regressed)}")

    # off_corpus must keep refusing.
    from src.eval.deepeval_runner import _is_refusal
    off_ref_b = sum(_is_refusal(base[q].get("answer", "")) for q in off_c)
    off_ref_t = sum(_is_refusal(treat[q].get("answer", "")) for q in off_c)
    print(f"off_corpus refusal: baseline {off_ref_b}/{len(off_c)} "
          f"→ treatment {off_ref_t}/{len(off_c)}")

    if recovered:
        print("\n  recuperadas:")
        for q in recovered:
            print(f"    + {q[:60]}")
    if regressed:
        print("\n  regresiones:")
        for q in regressed:
            print(f"    - {q[:60]}")


if __name__ == "__main__":
    main()
