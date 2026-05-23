"""Per-category metrics for the diverse eval set (queries_diverse.jsonl).

Each category measures a DISTINCT behaviour and is reported separately — never
aggregated. Consumes a saved deepeval results JSON.

  - categories with ground truth (definicional_canonico, fraseo_variado,
    alias_sigla, off_domain_corpus): recall@5 (norma+art), cited_expected,
    answered rate.
  - off_corpus: refusal rate (must be ~100%).
  - relacional / natural / ambiguo: no single ground truth → answered vs
    refusal only (qualitative; inspect manually).

Usage:
    PYTHONPATH=. ./venv/bin/python scripts/score_diverse.py --results <path>
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.eval.correctness import cited_expected
from src.eval.deepeval_runner import _is_refusal

HAS_TRUTH = {"definicional_canonico", "fraseo_variado", "alias_sigla",
             "off_domain_corpus"}
REFUSAL_EXPECTED = {"off_corpus"}
QUALITATIVE = {"relacional", "natural", "ambiguo"}


def _pct(p: int, n: int) -> str:
    return f"{100*p/n:.0f}%" if n else "—"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", type=Path, required=True)
    a = ap.parse_args()
    rows = json.loads(a.results.read_text(encoding="utf-8"))["per_query"]

    by_cat: dict[str, list] = defaultdict(list)
    for r in rows:
        by_cat[r.get("category") or "?"].append(r)

    print(f"=== {a.results.name} ===")
    print(f"{'categoría':22} {'n':>3} {'recall@5':>8} {'cita_ok':>8} "
          f"{'answered':>8} {'refusal':>8}")
    for cat in sorted(by_cat):
        rs = by_cat[cat]
        n = len(rs)
        answered = sum(not _is_refusal(r.get("answer", "")) for r in rs)
        refusal = n - answered
        line = f"{cat:22} {n:>3} "
        if cat in HAS_TRUTH:
            recall = sum(bool(r.get("retrieval_hit")) for r in rs)
            cited = sum(cited_expected(r.get("citations"), r.get("expected_norma"),
                                       r.get("expected_articulo")) for r in rs)
            line += f"{_pct(recall,n):>8} {_pct(cited,n):>8} "
        else:
            line += f"{'—':>8} {'—':>8} "
        line += f"{_pct(answered,n):>8} {_pct(refusal,n):>8}"
        print(line)

    print("\nLeer: HAS_TRUTH→recall/cita importan · off_corpus→refusal debe ser ~100% "
          "· relacional/natural/ambiguo→solo answered/refusal (juicio manual).")


if __name__ == "__main__":
    main()
