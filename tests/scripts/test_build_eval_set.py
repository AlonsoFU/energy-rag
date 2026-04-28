"""Unit tests for scripts.build_eval_set.

These are pure-data tests — they patch out DB calls so they run without any
infrastructure. They confirm the JSONL structure is valid for run_deepeval.
"""
import json
from pathlib import Path
from unittest.mock import patch

from scripts.build_eval_set import (
    HAND_CURATED,
    build,
    fetch_auto_queries,
)


def _fake_records():
    return [
        {
            "nombre": "Pórtico",
            "articulo_numero": "3",
            "id_norma": "1207690",
            "clase": "reglamento_base",
            "def_len": 117,
        },
        {
            "nombre": "Coordinador",
            "articulo_numero": "10",
            "id_norma": "1146553",
            "clase": "reglamento_base",
            "def_len": 200,
        },
    ]


def test_fetch_auto_queries_shape():
    fake_cur = type("Cur", (), {})()
    fake_cur.execute = lambda *a, **k: None
    fake_cur.fetchall = lambda: _fake_records()

    class _CM:
        def __enter__(self_inner): return self_inner
        def __exit__(self_inner, *_): return False

    class _FakeConn(_CM):
        def cursor(self_inner, **kwargs): return _CM.__enter__(_CM()) and fake_cur
    # Easier: patch with_connection's context-manager style.

    class _ConnCM:
        def __enter__(self_inner): return _ConnCM
        def __exit__(self_inner, *_): return False
        @staticmethod
        def cursor(**kwargs):
            class _C:
                def __enter__(s): return fake_cur
                def __exit__(s, *_): return False
            return _C()

    with patch("scripts.build_eval_set.with_connection", lambda: _ConnCM()):
        rows = fetch_auto_queries(limit=10)

    assert len(rows) == 2
    for r in rows:
        assert set(r.keys()) >= {"query", "expected_norma", "expected_articulo", "category"}
        assert r["query"].startswith("qué es ")
        assert r["category"] == "concept_definition_auto"
        assert r["expected_norma"]  # truthy, non-empty


def test_build_emits_valid_jsonl_for_run_deepeval(tmp_path):
    """The runner reads each line as JSON; verify our output is parseable
    and conforms to the schema run_deepeval expects."""
    fake_cur = type("Cur", (), {})()
    fake_cur.execute = lambda *a, **k: None
    # First call: SELECT id_norma FROM normas (verify_hand_curated)
    # Second call: the auto-queries SELECT
    # We make fetchall flip-flop:
    state = {"step": 0}
    needed_normas = [{"id_norma": h["expected_norma"]} for h in HAND_CURATED if h["expected_norma"]]
    auto_payload = _fake_records()

    def _fetchall():
        state["step"] += 1
        if state["step"] == 1:
            return needed_normas
        return auto_payload
    fake_cur.fetchall = _fetchall

    class _ConnCM:
        def __enter__(self_inner): return _ConnCM
        def __exit__(self_inner, *_): return False
        @staticmethod
        def cursor(**kwargs):
            class _C:
                def __enter__(s): return fake_cur
                def __exit__(s, *_): return False
            return _C()

    out = tmp_path / "queries.jsonl"
    with patch("scripts.build_eval_set.with_connection", lambda: _ConnCM()):
        n = build(limit=20, output=out)

    assert n > 0
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == n

    required = {"query", "expected_norma", "expected_articulo"}
    for r in rows:
        assert required.issubset(r.keys()), f"missing keys in row: {r}"
        # `query` must be non-empty string
        assert isinstance(r["query"], str) and r["query"].strip()
        # expected_norma null is allowed for negatives, otherwise must be a string
        assert r["expected_norma"] is None or isinstance(r["expected_norma"], str)
        # expected_articulo similarly
        assert r["expected_articulo"] is None or isinstance(r["expected_articulo"], str)


def test_hand_curated_has_negatives_and_diversity():
    cats = {h["category"] for h in HAND_CURATED}
    assert "negative" in cats
    # at least 5 distinct categories so the eval covers some breadth
    assert len(cats) >= 5
    # Negatives must have null expected_norma
    for h in HAND_CURATED:
        if h["category"] == "negative":
            assert h["expected_norma"] is None
