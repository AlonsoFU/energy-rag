"""Fase 0 — hard correctness over in_domain definitional queries.

Consumes a saved eval results JSON (from `run_deepeval(save_results=True)`)
and, for each in_domain row, scores:

  - cited_expected:    answer cites the expected (norma, articulo)  [exact]
  - definition_recall: fraction of the glossary definition present  [0..1]

The glossary definition is recovered from the DB: the query term is extracted
(`extract_definitional_term`), normalized (`normalize_for_match`) and looked
up against `conceptos.definicion`. This is the SAME deterministic matching
the inject path uses, so the mapping is consistent with what the system saw.

Off_corpus rows are scored separately for refusal (must be 100%).

Usage:
    ./venv/bin/python scripts/score_correctness.py \
        --results data/eval/results/<ts>.json \
        [--out data/eval/correctness_<ts>.json]
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache
from pathlib import Path
from statistics import mean, median

from src.eval.correctness import cited_expected, definition_recall
from src.eval.deepeval_runner import _is_refusal
from src.pipelines.concept_injection import extract_definitional_term
from src.pipelines.normalize import normalize_for_match
from src.storage.connection import with_connection


@lru_cache(maxsize=1)
def _definition_index() -> dict[str, str]:
    """`{normalized_concept_name_or_alias: definicion}`. Same normalization
    as the inject path so the mapping matches what the system used."""
    out: dict[str, str] = {}
    with with_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT nombre, aliases, definicion FROM conceptos")
        for nombre, aliases, definicion in cur.fetchall():
            if not definicion:
                continue
            for name in [nombre, *(aliases or [])]:
                key = normalize_for_match(str(name))
                if key:
                    out.setdefault(key, definicion)
    return out


def _definition_for_query(query: str) -> str | None:
    term = extract_definitional_term(query)
    if term is None:
        return None
    return _definition_index().get(normalize_for_match(term))


def _pct(part: int, whole: int) -> float:
    return (100.0 * part / whole) if whole else 0.0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", type=Path, required=True)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--def-recall-strong", type=float, default=0.6,
                   help="threshold for the combined strict-correct metric")
    a = p.parse_args()

    data = json.loads(a.results.read_text(encoding="utf-8"))
    rows = data["per_query"]

    in_domain = [r for r in rows if r.get("category") == "in_domain"]
    off_corpus = [r for r in rows if r.get("category") == "off_corpus"]

    scored: list[dict] = []
    unmapped = 0
    for r in in_domain:
        definition = _definition_for_query(r["query"])
        if definition is None:
            unmapped += 1
            continue
        cited = cited_expected(
            r.get("citations"), r.get("expected_norma"), r.get("expected_articulo"))
        drec = definition_recall(r.get("answer", ""), definition)
        scored.append({
            "query": r["query"],
            "expected_norma": r.get("expected_norma"),
            "expected_articulo": r.get("expected_articulo"),
            "cited_expected": cited,
            "definition_recall": round(drec, 3),
            "answered": not _is_refusal(r.get("answer", "")),
        })

    n = len(scored)
    cited_n = sum(s["cited_expected"] for s in scored)
    recalls = [s["definition_recall"] for s in scored]
    strong = a.def_recall_strong
    drec_ge_strong = sum(r >= strong for r in recalls)
    drec_ge_80 = sum(r >= 0.8 for r in recalls)
    # Combined HARD correctness: cites the right article AND reproduces the
    # substance of the definition.
    strict_correct = sum(
        s["cited_expected"] and s["definition_recall"] >= strong for s in scored)

    off_refusal = sum(_is_refusal(r.get("answer", "")) for r in off_corpus)

    report = {
        "results_file": str(a.results),
        "in_domain_scored": n,
        "in_domain_unmapped": unmapped,
        "cited_expected_pct": round(_pct(cited_n, n), 1),
        "definition_recall_mean": round(mean(recalls), 3) if recalls else 0.0,
        "definition_recall_median": round(median(recalls), 3) if recalls else 0.0,
        f"definition_recall_ge_{strong}_pct": round(_pct(drec_ge_strong, n), 1),
        "definition_recall_ge_0.8_pct": round(_pct(drec_ge_80, n), 1),
        "strict_correct_pct": round(_pct(strict_correct, n), 1),
        "strict_correct_def": f"cited_expected AND definition_recall>={strong}",
        "off_corpus_n": len(off_corpus),
        "off_corpus_refusal_pct": round(_pct(off_refusal, len(off_corpus)), 1),
        "per_query": scored,
    }

    print(json.dumps({k: v for k, v in report.items() if k != "per_query"},
                     ensure_ascii=False, indent=2))

    # Worst offenders for inspection.
    worst = sorted(scored, key=lambda s: s["definition_recall"])[:10]
    print("\n--- 10 peores por definition_recall ---")
    for s in worst:
        print(f"  {s['definition_recall']:.2f}  cited={s['cited_expected']!s:5} "
              f"{s['query'][:60]}")

    out = a.out or a.results.with_name(a.results.stem + "_correctness.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nescrito: {out}")


if __name__ == "__main__":
    main()
