"""Real eval runner over a JSONL eval set.

Each JSONL line is `{"query", "expected_norma", "expected_articulo", "category"}`.
``expected_norma`` may be null for negative (out-of-domain) queries — in that
case the system is expected to refuse with an "no encuentro" sentinel.

The runner exercises an `AdaptiveRetriever`-shaped object (`.retrieve(query,
top_k) -> (branch, list[doc])`) plus an LLM. It produces three families of
metrics: retrieval (recall@k), generation (grounding pass / answered /
negative-correct) and latency (p50/p95/p99). Full per-query traces are kept
so failures can be inspected after the fact.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import quantiles
from typing import Any, Callable, Iterable

# Sentinel substring the answer prompt instructs the LLM to emit when it
# cannot answer. Matched case-insensitively in `_is_refusal`.
REFUSAL_PHRASE = "no encuentro esa información"


def _norm_articulo(value: Any) -> str:
    """Normalize an articulo number for equality comparison.

    Handles:
    - degree sign trailing ("5°" -> "5")
    - tokens like "5°a" -> "5a"
    - whitespace
    - numeric-vs-string ("5" vs 5)
    """
    if value is None:
        return ""
    s = str(value).strip()
    return s.replace("°", "")


def _is_refusal(text: str) -> bool:
    """Did the model decline to answer? Case-insensitive substring check."""
    return REFUSAL_PHRASE.lower() in (text or "").lower()


def _retrieval_hit(docs: list[dict], expected_norma: str | None,
                    expected_articulo: str | None) -> tuple[bool, bool]:
    """Return (full_hit, norma_only_hit) for the retrieval candidate list.

    `full_hit` requires both norma and articulo to match (or articulo to be
    unspecified). `norma_only_hit` just needs the norma to be present.
    """
    if expected_norma is None:
        return (False, False)
    norma_only = any(d.get("id_norma") == expected_norma for d in docs)
    if expected_articulo is None:
        return (norma_only, norma_only)
    target = _norm_articulo(expected_articulo)
    full = any(
        d.get("id_norma") == expected_norma
        and _norm_articulo(d.get("articulo_numero")) == target
        for d in docs
    )
    return (full, norma_only)


def _percentiles(values: list[int]) -> dict[str, int]:
    """Return p50/p95/p99 in ms. Empty input -> all zeros."""
    if not values:
        return {"p50": 0, "p95": 0, "p99": 0}
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        v = sorted_vals[0]
        return {"p50": v, "p95": v, "p99": v}
    # quantiles with n=100 returns 99 cutpoints: index 49 ~ p50, 94 ~ p95, 98 ~ p99
    qs = quantiles(sorted_vals, n=100, method="inclusive")
    return {
        "p50": int(qs[49]),
        "p95": int(qs[94]),
        "p99": int(qs[98]),
    }


def run_deepeval(
    eval_file: Path | str,
    retriever,
    *,
    top_k: int = 5,
    llm: Any = None,
    model: str | None = None,
    save_results: bool = False,
    results_dir: Path | str = "data/eval/results",
    progress: Callable[[int, int, dict], None] | None = None,
) -> dict:
    """Run the eval suite end-to-end and return the metrics dict.

    Parameters
    ----------
    eval_file:
        Path to a JSONL file with one query per line.
    retriever:
        Anything exposing ``.retrieve(query, top_k) -> (branch, docs)`` —
        typically an ``AdaptiveRetriever``.
    top_k:
        How many docs to retrieve / measure recall against.
    llm:
        LLM provider. If ``None``, only retrieval + grounding-aware metrics
        that need a generation will be skipped (everything generation-related
        will be reported as 0).
    model:
        Optional override for the LLM model id. If unset, ``generate_answer``
        picks per-branch defaults from settings.
    save_results:
        When true, write the full result dict to ``results_dir/<iso>.json``.
    progress:
        Optional callback invoked after each query: ``(idx, total, row)``.
    """
    # Lazy imports keep this module cheap to import (used by tests)
    from src.pipelines.generate import generate_answer
    from src.pipelines.grounding import extract_citations

    eval_file = Path(eval_file)
    queries = [
        json.loads(line)
        for line in eval_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    per_query: list[dict] = []
    latencies: list[int] = []

    retrieval_full_hits = 0
    retrieval_norma_hits = 0
    grounding_passes = 0
    answered = 0  # i.e. did NOT refuse
    negatives = 0
    negative_correct = 0
    n_with_generation = 0  # how many queries we actually ran the LLM on
    n_positive = 0  # queries where a hit is even possible (expected_norma not null)

    for idx, q in enumerate(queries):
        expected_norma = q.get("expected_norma")
        expected_articulo = q.get("expected_articulo")

        t0 = time.time()
        try:
            branch, docs = retriever.retrieve(q["query"], top_k=top_k)
        except Exception as exc:  # pragma: no cover - defensive
            branch, docs = "error", []
            err = str(exc)
        else:
            err = None
        retrieval_ms = int((time.time() - t0) * 1000)

        full_hit, norma_only = _retrieval_hit(docs, expected_norma, expected_articulo)
        if expected_norma is not None:
            n_positive += 1
            if full_hit:
                retrieval_full_hits += 1
            if norma_only:
                retrieval_norma_hits += 1
        else:
            negatives += 1

        # Generation pass — only run when we have docs AND an LLM. If retrieval
        # missed for a positive query, grounding cannot pass, so we skip the
        # LLM call to save time (this is documented in step 5 of the brief).
        answer_text = ""
        grounding_pass = False
        citations: list[tuple[str, str]] = []
        gen_ms = 0
        if llm is not None and docs:
            should_generate = (expected_norma is None) or full_hit
            if should_generate:
                t1 = time.time()
                try:
                    result = generate_answer(q["query"], docs, llm=llm, model=model)
                    answer_text = result["text"]
                    grounding_pass = result["grounding_pass"]
                except Exception as exc:  # pragma: no cover - defensive
                    err = err or f"generate_error: {exc}"
                gen_ms = int((time.time() - t1) * 1000)
                n_with_generation += 1
                citations = extract_citations(answer_text)
                if grounding_pass:
                    grounding_passes += 1
                if not _is_refusal(answer_text):
                    answered += 1
                if expected_norma is None and _is_refusal(answer_text):
                    negative_correct += 1

        total_ms = retrieval_ms + gen_ms
        latencies.append(total_ms)

        row = {
            "query": q["query"],
            "category": q.get("category"),
            "expected_norma": expected_norma,
            "expected_articulo": expected_articulo,
            "branch": branch,
            "retrieval_hit": full_hit,
            "retrieval_norma_only_hit": norma_only,
            "grounding_pass": grounding_pass,
            "latency_ms": total_ms,
            "retrieval_ms": retrieval_ms,
            "generation_ms": gen_ms,
            "answer": answer_text,
            "citations": citations,
            "n_docs": len(docs),
            "top_doc": (
                {"id_norma": docs[0].get("id_norma"),
                 "articulo_numero": docs[0].get("articulo_numero")}
                if docs else None
            ),
            "error": err,
        }
        per_query.append(row)
        if progress is not None:
            progress(idx + 1, len(queries), row)

    n = len(queries)
    metrics = {
        "n_queries": n,
        "n_positive": n_positive,
        "n_negative": negatives,
        "n_with_generation": n_with_generation,
        "retrieval": {
            "recall_at_5": (retrieval_full_hits / n_positive) if n_positive else 0.0,
            "recall_norma_only": (retrieval_norma_hits / n_positive) if n_positive else 0.0,
        },
        "generation": {
            "grounding_pass": (grounding_passes / n_with_generation) if n_with_generation else 0.0,
            "answered": (answered / n_with_generation) if n_with_generation else 0.0,
            "negative_correct": (negative_correct / negatives) if negatives else 0.0,
        },
        "latency_ms": _percentiles(latencies),
        "per_query": per_query,
    }

    if save_results:
        out_dir = Path(results_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = out_dir / f"{ts}.json"
        target.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        metrics["results_path"] = str(target)

    return metrics


def render_summary(metrics: dict) -> None:
    """Pretty-print the metrics dict to stdout via rich."""
    from rich import print as rprint
    from rich.table import Table

    t = Table(title=f"Eval results — {metrics['n_queries']} queries")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right")

    r = metrics["retrieval"]
    g = metrics["generation"]
    lat = metrics["latency_ms"]

    t.add_row("n_queries", str(metrics["n_queries"]))
    t.add_row("n_positive", str(metrics["n_positive"]))
    t.add_row("n_negative", str(metrics["n_negative"]))
    t.add_row("n_with_generation", str(metrics["n_with_generation"]))
    t.add_row("recall@5 (norma+articulo)", f"{r['recall_at_5']*100:.1f}%")
    t.add_row("recall@5 (norma-only)", f"{r['recall_norma_only']*100:.1f}%")
    t.add_row("grounding_pass", f"{g['grounding_pass']*100:.1f}%")
    t.add_row("answered (non-refusal)", f"{g['answered']*100:.1f}%")
    t.add_row("negative_correct", f"{g['negative_correct']*100:.1f}%")
    t.add_row("latency p50 (ms)", str(lat["p50"]))
    t.add_row("latency p95 (ms)", str(lat["p95"]))
    t.add_row("latency p99 (ms)", str(lat["p99"]))
    rprint(t)
