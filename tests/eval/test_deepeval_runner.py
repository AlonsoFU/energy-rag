from unittest.mock import MagicMock, patch


def test_deepeval_runs_on_minimal_set(tmp_path):
    """Smoke: runner accepts queries+expected and returns a metrics dict with the new shape."""
    from src.eval.deepeval_runner import run_deepeval
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query": "test", "expected_norma": "X", "expected_articulo": "1"}\n'
    )
    fake_retriever = MagicMock()
    fake_retriever.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "..."}
    ])
    metrics = run_deepeval(eval_file=eval_file, retriever=fake_retriever)
    assert metrics["n_queries"] == 1
    assert metrics["retrieval"]["recall_at_5"] == 1.0
    assert metrics["retrieval"]["recall_norma_only"] == 1.0
    # No LLM provided -> generation block is all zeros.
    assert metrics["generation"]["grounding_pass"] == 0.0
    assert "per_query" in metrics
    assert metrics["per_query"][0]["retrieval_hit"] is True


def test_deepeval_recall_zero_on_no_match(tmp_path):
    from src.eval.deepeval_runner import run_deepeval
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text('{"query": "test", "expected_norma": "X", "expected_articulo": "1"}\n')
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "OTHER", "articulo_numero": "99", "articulo_text": "..."}
    ])
    metrics = run_deepeval(eval_file=eval_file, retriever=fake)
    assert metrics["retrieval"]["recall_at_5"] == 0.0


def test_deepeval_articulo_none_means_norma_only(tmp_path):
    """When expected_articulo is null, just having the right norma counts as a hit."""
    from src.eval.deepeval_runner import run_deepeval
    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text('{"query": "test", "expected_norma": "X", "expected_articulo": null}\n')
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "99", "articulo_text": "..."}
    ])
    metrics = run_deepeval(eval_file=eval_file, retriever=fake)
    assert metrics["retrieval"]["recall_at_5"] == 1.0


def test_deepeval_metrics_shape_full(tmp_path):
    """Verify the metrics dict has every key callers depend on."""
    from src.eval.deepeval_runner import run_deepeval

    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query": "q1", "expected_norma": "X", "expected_articulo": "1", "category": "a"}\n'
        '{"query": "q2", "expected_norma": null, "expected_articulo": null, "category": "negative"}\n'
    )
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "t"}
    ])
    m = run_deepeval(eval_file=eval_file, retriever=fake)

    # Top-level keys
    for k in ("n_queries", "n_positive", "n_negative", "n_with_generation",
              "retrieval", "generation", "latency_ms", "per_query"):
        assert k in m, f"missing top-level key: {k}"
    for k in ("recall_at_5", "recall_norma_only"):
        assert k in m["retrieval"]
    for k in ("grounding_pass", "answered", "negative_correct"):
        assert k in m["generation"]
    for k in ("p50", "p95", "p99"):
        assert k in m["latency_ms"]
    row = m["per_query"][0]
    for k in ("query", "category", "expected_norma", "expected_articulo",
              "branch", "retrieval_hit", "grounding_pass", "latency_ms",
              "answer", "citations"):
        assert k in row, f"missing per-query key: {k}"


def test_deepeval_negative_correct_with_refusal(tmp_path):
    """Negative query: LLM refuses -> negative_correct = 100%."""
    from src.eval.deepeval_runner import run_deepeval

    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query": "q neg", "expected_norma": null, "expected_articulo": null}\n'
    )
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "t"}
    ])
    fake_llm = MagicMock()
    with patch(
        "src.pipelines.generate.generate_answer",
        return_value={
            "text": "No encuentro esa información en las normas disponibles.",
            "grounding_pass": False,
            "model": "mock",
            "tokens_in": 1,
            "tokens_out": 1,
        },
    ):
        m = run_deepeval(eval_file=eval_file, retriever=fake, llm=fake_llm)

    assert m["generation"]["negative_correct"] == 1.0


def test_deepeval_grounding_counted_when_llm_passes(tmp_path):
    """Positive query w/ hit + LLM grounding pass -> grounding_pass = 100%."""
    from src.eval.deepeval_runner import run_deepeval

    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query": "q1", "expected_norma": "X", "expected_articulo": "1"}\n'
    )
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "t"}
    ])
    fake_llm = MagicMock()
    with patch(
        "src.pipelines.generate.generate_answer",
        return_value={
            "text": "Yes [Art. 1 de X].",
            "grounding_pass": True,
            "model": "mock",
            "tokens_in": 1,
            "tokens_out": 1,
        },
    ):
        m = run_deepeval(eval_file=eval_file, retriever=fake, llm=fake_llm)

    assert m["generation"]["grounding_pass"] == 1.0
    assert m["generation"]["answered"] == 1.0
    assert m["per_query"][0]["citations"] == [("X", "1")]


def test_deepeval_save_results_writes_file(tmp_path):
    from src.eval.deepeval_runner import run_deepeval

    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text(
        '{"query": "q", "expected_norma": "X", "expected_articulo": "1"}\n'
    )
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "1", "articulo_text": "t"}
    ])
    out_dir = tmp_path / "results"
    m = run_deepeval(
        eval_file=eval_file, retriever=fake,
        save_results=True, results_dir=out_dir,
    )
    assert "results_path" in m
    saved_files = list(out_dir.glob("*.json"))
    assert len(saved_files) == 1


def test_deepeval_normalizes_articulo_with_degree_sign(tmp_path):
    """Expected '5' should match retrieved '5°'."""
    from src.eval.deepeval_runner import run_deepeval

    eval_file = tmp_path / "eval.jsonl"
    eval_file.write_text('{"query": "q", "expected_norma": "X", "expected_articulo": "5"}\n')
    fake = MagicMock()
    fake.retrieve.return_value = ("simple", [
        {"id_norma": "X", "articulo_numero": "5°", "articulo_text": "t"}
    ])
    m = run_deepeval(eval_file=eval_file, retriever=fake)
    assert m["retrieval"]["recall_at_5"] == 1.0
